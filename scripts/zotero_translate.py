"""Hermes academic translation entry point. No success without verified artifacts."""
from __future__ import annotations
import argparse
import difflib
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from adapters import CPAAdapter,DeepSeekAdapter,OllamaAdapter
from scripts.latex_syntax import ProjectPlan,IntegrityError,mask_latex_tokens,unmask_latex_tokens
from scripts.latex_compiler import compile_latex_project,find_main_tex,make_side_by_side_dual_pdf,pack_source_zip
from scripts.project_utils import atomic_json,copy_project,pdf_info,project_files,safe_extract_tar,sha256

DEFAULT_PROMPT_TEMPLATE=(ROOT/'prompts/zotero_default.txt').read_text(encoding='utf-8')
ARXIV_RE=re.compile(r'(?<![\w])((?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v\d+)?)(?![\w])',re.I)


def load_config(path=None):
    path=Path(path or os.getenv('ACADEMIC_TRANSLATE_CONFIG',str(ROOT/'config.local.json')))
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def get_adapter(provider='cpa',config=None):
    config=load_config() if config is None else config
    cls={'cpa':CPAAdapter,'deepseek':DeepSeekAdapter,'ollama':OllamaAdapter}[provider]
    options={k:v for k,v in config.get('providers',{}).get(provider,{}).items() if k in {'base_url','api_key','model','timeout','attempts'} and v is not None}
    prefix=provider.upper()
    for key in ['api_key','base_url','model']:
        if os.getenv(prefix+'_'+key.upper()) is not None:options[key]=os.environ[prefix+'_'+key.upper()]
    return cls(**options)


def _download(url,target,limit=200*1024*1024):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(url,headers={'User-Agent':'academic-paper-translate/2.0 (research source retrieval)'})
    temp=target.with_name(target.name+'.download')
    try:
        with urllib.request.urlopen(req,timeout=45) as response,open(temp,'wb') as f:
            total=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>limit:raise ValueError('Download exceeds size limit')
                f.write(chunk)
        os.replace(temp,target)
    finally:
        if temp.exists():temp.unlink()


def find_arxiv_id_from_pdf(pdf_path):
    import pymupdf
    with pymupdf.open(str(pdf_path)) as doc:
        text='\n'.join(doc[i].get_text() for i in range(min(3,len(doc))))
    match=re.search(r'arxiv(?:\s*:\s*|\.org/(?:abs|pdf)/)'+ARXIV_RE.pattern,text,re.I)
    return match.group(1) if match else None


def search_arxiv_by_title(title):
    normalized=lambda s:re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
    clean=normalized(title)
    if len(clean)<5:return None
    query=urllib.parse.urlencode({'search_query':'ti:"'+' '.join(clean.split()[:16])+'"','max_results':5})
    req=urllib.request.Request('https://export.arxiv.org/api/query?'+query,headers={'User-Agent':'academic-paper-translate/2.0'})
    with urllib.request.urlopen(req,timeout=30) as response:root=ET.fromstring(response.read())
    ns={'a':'http://www.w3.org/2005/Atom'};matches=[]
    for entry in root.findall('a:entry',ns):
        found=entry.findtext('a:title','',ns);identifier=entry.findtext('a:id','',ns)
        m=ARXIV_RE.search(identifier)
        score=difflib.SequenceMatcher(None,clean,normalized(found)).ratio()
        if m and score>=0.90:matches.append((score,m.group(1)))
    matches.sort(reverse=True)
    if len(matches)>1 and matches[0][0]-matches[1][0]<0.03:raise ValueError('Ambiguous title match; supply arXiv ID')
    return matches[0][1] if matches else None


def download_arxiv_pdf(arxiv_id,target_pdf_path):
    try:
        _download('https://arxiv.org/pdf/'+arxiv_id,target_pdf_path)
        pdf_info(target_pdf_path);return True
    except Exception as e:
        print('Original PDF unavailable:',type(e).__name__);return False


def fetch_arxiv_source(arxiv_id,target_dir):
    target=Path(target_dir);target.mkdir(parents=True,exist_ok=True)
    archive=target.parent/(target.name+'.download.gz')
    try:
        _download('https://arxiv.org/e-print/'+arxiv_id,archive)
        header=archive.read_bytes()[:8]
        if header.startswith(b'%PDF'):return False
        if tarfile.is_tarfile(archive):safe_extract_tar(archive,target)
        else:
            if header.startswith(b'\x1f\x8b'):
                with gzip.open(archive,'rb') as f:data=f.read(64*1024*1024+1)
            else:data=archive.read_bytes()
            if len(data)>64*1024*1024 or data.startswith(b'%PDF'):return False
            text=data.decode('utf-8')
            if '\\documentclass' not in text:return False
            (target/'main.tex').write_bytes(data)
        return bool(find_main_tex(target))
    except Exception as e:
        print('Source unavailable:',type(e).__name__,str(e)[:200]);return False
    finally:
        if archive.exists():archive.unlink()


def process_latex_project(project_dir,adapter=None,prompt_template=None,max_workers=4,main_tex=None,cache_path=None):
    if not 1<=max_workers<=16:raise ValueError('workers must be between 1 and 16')
    adapter=adapter or get_adapter();prompt_template=prompt_template or DEFAULT_PROMPT_TEMPLATE
    root=Path(project_dir).resolve();main=Path(main_tex or find_main_tex(root))
    plan=ProjectPlan(root,main)
    if not plan.segments:raise IntegrityError('No translatable English prose was found')
    namespace=hashlib.sha256((getattr(adapter,'base_url','')+getattr(adapter,'model','test')+prompt_template).encode()).hexdigest()
    cache={}
    if cache_path and Path(cache_path).exists():
        try:cache=json.loads(Path(cache_path).read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    answers={};cached=0
    unique={s.key:s for s in plan.segments}
    todo=[]
    for key,s in unique.items():
        ck=namespace+':'+key
        try:
            s.restore(cache[ck]);answers[key]=cache[ck];cached+=1
        except (KeyError,ValueError):todo.append(s)

    def worker(segment):
        error=None
        for attempt in range(2):
            try:
                answer=adapter.translate(segment.masked,prompt_template)
                segment.restore(answer)
                return segment.key,answer
            except (IntegrityError,ValueError) as e:error=e
        raise IntegrityError(f'Translation validation failed at {segment.path.name}:{segment.start}: {error}')

    executor=ThreadPoolExecutor(max_workers=max_workers)
    futures=[executor.submit(worker,s) for s in todo]
    try:
        for future in as_completed(futures):
            key,answer=future.result();answers[key]=answer;cache[namespace+':'+key]=answer
            if cache_path:atomic_json(cache_path,cache)
    except BaseException:
        # Stop queued API calls on the first terminal failure. At most the
        # already-running, individually time-bounded requests must finish.
        for future in futures:future.cancel()
        raise
    finally:
        executor.shutdown(wait=True,cancel_futures=True)
    updated=plan.apply(answers)
    # Validate ALL replacements before touching even the disposable work copy.
    sources=[{'file':str(p.relative_to(root)),'before_sha256':hashlib.sha256(t.encode()).hexdigest(),'after_sha256':hashlib.sha256(updated[p].encode()).hexdigest()} for p,t in plan.sources.items()]
    for p,value in updated.items():p.write_bytes(value.encode('utf-8'))
    report={'segments':len(plan.segments),'translated':len(plan.segments),'unique_segments':len(unique),'cache_hits':cached,'protected_content_verified':True,'sources':sources,'spans':[{'file':str(s.path.relative_to(root)),'start':s.start,'end':s.end,'kind':s.kind,'protected_tokens':len(s.mapping)} for s in plan.segments]}
    print(f'Translated and validated {len(plan.segments)} prose spans; frozen syntax restored exactly.')
    return report


def translate_tex_file(file_path,output_path=None,adapter=None,prompt_template=None,max_workers=4):
    # Compatibility helper: explicit output is required to protect original data.
    import tempfile
    source=Path(file_path).resolve()
    if output_path is None or Path(output_path).resolve()==source:raise ValueError('Use a different output_path; input is read-only')
    with tempfile.TemporaryDirectory() as td:
        copy_project(source.parent,td)
        target=Path(td)/source.name
        report=process_latex_project(td,adapter,prompt_template,max_workers,main_tex=target)
        Path(output_path).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,output_path)
    return report


def _identity(target,original=None,exclude=()):
    p=Path(target)
    if p.is_file():return 'file:'+str(p.resolve())+':'+sha256(p)
    if p.is_dir():
        excluded=[p/'translated',p/'.translation',*exclude]
        values=[(str(f.relative_to(p.resolve())),sha256(f)) for f in project_files(p,excluded)]
        return 'project:'+str(p.resolve())+':'+hashlib.sha256(json.dumps(values).encode()).hexdigest()
    return 'query:'+target.strip()


def _auto_translate_paper(input_target,output_dir=None,provider='cpa',max_workers=4,config=None,original=None,main_tex=None,no_fallback=False,prompt_name='zotero_default',compile_timeout=180):
    config=load_config() if config is None else config
    target=Path(input_target).expanduser()
    final=Path(output_dir or ((target if target.is_dir() else target.parent)/(target.stem+'_translated') if target.exists() else Path.cwd()/('paper_'+hashlib.sha256(input_target.encode()).hexdigest()[:10]))).resolve()
    if target.is_dir() and final==target.resolve():raise ValueError('Output cannot be the original project directory')
    final.mkdir(parents=True,exist_ok=True)
    identity=_identity(input_target,original,exclude=[final])
    if original:
        if not Path(original).is_file():raise ValueError('Explicit original PDF does not exist')
        identity+=':original:'+sha256(original)
    previous=final/'translation_manifest.json'
    if previous.exists():
        if json.loads(previous.read_text(encoding='utf-8')).get('input_identity')!=identity:raise ValueError('Output belongs to different input; choose a new directory')
    elif any((final/name).exists() for name in ['chinese_mono.pdf','original.pdf','chinese_source.zip','bilingual_dual.pdf']):
        raise ValueError('Untracked existing artifacts in output; use an empty directory')
    run=final/'.translation'/'runs'/uuid.uuid4().hex;run.mkdir(parents=True)
    manifest={'schema_version':2,'skill_version':(ROOT/'VERSION').read_text(encoding='utf-8').strip(),'input_identity':identity,'status':'running','input':str(input_target),'provider':provider,'run_dir':str(run),'errors':[],'warnings':[]}
    atomic_json(previous,manifest)
    originals=run/'original.pdf';source=None;arxiv_id=None;translated=None
    try:
        import pymupdf
        if target.is_dir():
            source=copy_project(target,run/'source',exclude=[final])
            candidate=Path(original) if original else target/'original.pdf'
            if candidate.is_file():shutil.copy2(candidate,originals);manifest['original_provenance']='user_supplied_pdf'
        elif target.is_file() and target.suffix.lower()=='.pdf':
            shutil.copy2(target,originals);manifest['original_provenance']='user_supplied_pdf'
            try:
                arxiv_id=find_arxiv_id_from_pdf(target)
                if not arxiv_id:
                    name_match=ARXIV_RE.search(target.stem)
                    if name_match:
                        arxiv_id=name_match.group(1)
                        manifest['warnings'].append('arXiv ID inferred from local filename; supplied PDF retained as original.')
                if not arxiv_id:
                    with pymupdf.open(str(target)) as d:title=d.metadata.get('title','')
                    if title and len(title)>10:arxiv_id=search_arxiv_by_title(title)
            except Exception as e:manifest['warnings'].append('Source lookup failed: '+type(e).__name__)
        elif target.exists():raise ValueError('Input must be a PDF or TeX project directory')
        else:
            m=ARXIV_RE.search(input_target)
            arxiv_id=m.group(1) if m else search_arxiv_by_title(input_target)
            if not arxiv_id:raise ValueError('No confident arXiv match for input')
        if arxiv_id:
            manifest['arxiv_id']=arxiv_id
            if not originals.exists() and download_arxiv_pdf(arxiv_id,originals):manifest['original_provenance']='arxiv_pdf'
            if fetch_arxiv_source(arxiv_id,run/'source'):source=run/'source'
        if source and not main_tex and not find_main_tex(source):
            manifest['errors'].append({'stage':'source','detail':'No usable TeX entry'})
            pack_source_zip(source,run/'chinese_source_uncompiled.zip')
            source=None
        if source:
            entry=(source/main_tex).resolve() if main_tex else Path(find_main_tex(source) or '')
            if not entry.is_file():raise ValueError('No valid TeX entry')
            if not originals.exists():
                ok,built,log=compile_latex_project(source,entry,timeout=compile_timeout,chinese=False)
                manifest['original_compile']=json.loads(log) if log.startswith('{') else {'error':log}
                if ok:
                    shutil.copy2(built,originals);manifest['original_provenance']='recompiled_untouched_source'
                    manifest['warnings'].append('Original PDF was rebuilt from source; it is not an independently obtained official PDF.')
                else:manifest['errors'].append({'stage':'original_compile','detail':log})
            translated=copy_project(source,run/'translated')
            entry=translated/entry.relative_to(source)
            try:
                prompt=ROOT/'prompts'/(prompt_name+'.txt')
                if not prompt.resolve().is_relative_to(ROOT/'prompts') or not prompt.exists():raise ValueError('Unknown prompt')
                adapter=get_adapter(provider,config)
                manifest['model']=adapter.model
                manifest['translation']=process_latex_project(translated,adapter,prompt.read_text(encoding='utf-8'),max_workers,entry,final/'.translation'/'cache.json')
                ok,built,log=compile_latex_project(translated,entry,timeout=compile_timeout)
                manifest['compile']=json.loads(log) if log.startswith('{') else {'error':log}
                if not ok:raise RuntimeError('Native compilation did not pass: '+log)
                if not originals.exists():raise RuntimeError('Original PDF unavailable for bilingual delivery')
                shutil.copy2(built,run/'chinese_mono.pdf')
                make_side_by_side_dual_pdf(originals,run/'chinese_mono.pdf',run/'bilingual_dual.pdf')
                pack_source_zip(translated,run/'chinese_source.zip')
                # Rebuild the delivered archive, not merely the working tree.
                import zipfile
                rebuild=run/'archive_rebuild';rebuild.mkdir()
                with zipfile.ZipFile(run/'chinese_source.zip') as z:z.extractall(rebuild)
                ok,_,rebuild_log=compile_latex_project(rebuild,rebuild/entry.relative_to(translated),timeout=compile_timeout)
                manifest['archive_rebuild']={'success':ok,'details':rebuild_log}
                if not ok:raise RuntimeError('Archived source cannot be rebuilt')
                manifest['mode']='latex_native'
            except Exception as e:
                manifest['errors'].append({'stage':'native','detail':str(e)[:10000]})
                pack_source_zip(translated,run/'chinese_source_uncompiled.zip')
        if manifest.get('mode')!='latex_native':
            if no_fallback:raise RuntimeError('Native mode failed; fallback disabled')
            if not originals.exists():raise RuntimeError('No valid original PDF for fallback')
            from scripts.pdf_runner import run_pdf_translation
            if not run_pdf_translation(str(originals),str(run),qps=max_workers,config=config,provider=provider):
                raise RuntimeError('PDF fallback did not produce verified artifacts')
            manifest['mode']='pdf_fallback'
            manifest['warnings'].append('PDF fallback does not provide byte-level TeX/table integrity guarantees.')
        required=['original.pdf','chinese_mono.pdf','bilingual_dual.pdf']
        info={name:pdf_info(run/name) for name in required}
        if info['bilingual_dual.pdf']['pages']!=max(info['original.pdf']['pages'],info['chinese_mono.pdf']['pages']):raise ValueError('Dual page count mismatch')
        if info['original.pdf']['pages']!=info['chinese_mono.pdf']['pages']:manifest['warnings'].append('English and Chinese page counts differ; all pages retained, paired by page index.')
        with pymupdf.open(str(run/'chinese_mono.pdf')) as d:
            if not any(re.search(r'[\u3400-\u9fff]',p.get_text()) for p in d):raise ValueError('Chinese PDF has no extractable Chinese text')
        if manifest['mode']=='latex_native':required.append('chinese_source.zip')
        elif (run/'chinese_source_uncompiled.zip').exists():required.append('chinese_source_uncompiled.zip')
        for name in required:shutil.copy2(run/name,final/name)
        manifest['artifacts']={name:(info[name] if name in info else {'sha256':sha256(final/name),'bytes':(final/name).stat().st_size}) for name in required}
        warnings=manifest.get('compile',{}).get('layout_warnings',[])
        manifest['warnings'].extend(warnings)
        manifest['status']='review_required' if warnings else ('complete_native' if manifest['mode']=='latex_native' else 'complete_fallback')
        atomic_json(previous,manifest)
        print('Translation status:',manifest['status'])
        print('Verified output:',final)
        return manifest['status'] in {'complete_native','complete_fallback'}
    except Exception as e:
        manifest['status']='failed';manifest['errors'].append({'stage':'workflow','detail':str(e)[:10000]})
        if (run/'chinese_source_uncompiled.zip').exists():shutil.copy2(run/'chinese_source_uncompiled.zip',final/'chinese_source_uncompiled.zip')
        atomic_json(previous,manifest)
        print('Translation failed:',str(e)[:1200]);return False


def auto_translate_paper(input_target,output_dir=None,provider='cpa',max_workers=4,config=None,original=None,main_tex=None,no_fallback=False,prompt_name='zotero_default',compile_timeout=180):
    if not 1<=max_workers<=16:raise ValueError('workers must be between 1 and 16')
    target=Path(input_target).expanduser()
    final=Path(output_dir or ((target if target.is_dir() else target.parent)/(target.stem+'_translated') if target.exists() else Path.cwd()/('paper_'+hashlib.sha256(input_target.encode()).hexdigest()[:10]))).resolve()
    if target.is_dir() and final==target.resolve():raise ValueError('Output cannot be the original project directory')
    lock=final/'.translation'/'active.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise ValueError('Output directory is locked by another run: '+str(lock)) from None
    try:
        with os.fdopen(fd,'w') as f:f.write(json.dumps({'pid':os.getpid(),'started':time.time()}))
        return _auto_translate_paper(input_target,final,provider,max_workers,config,original,main_tex,no_fallback,prompt_name,compile_timeout)
    finally:
        if lock.exists():lock.unlink()


def doctor():
    import importlib.util
    checks={'python':sys.executable,'python_version':sys.version.split()[0],'pymupdf':bool(importlib.util.find_spec('pymupdf')),'xelatex':shutil.which('xelatex'),'bibtex':shutil.which('bibtex'),'biber':shutil.which('biber'),'uv':shutil.which('uv')}
    print(json.dumps(checks,ensure_ascii=False,indent=2))
    return checks['pymupdf'] and bool(checks['xelatex'])


def main():
    p=argparse.ArgumentParser(description='Hermes verified academic paper translation')
    group=p.add_mutually_exclusive_group()
    for flag in ['--input','--arxiv','--dir','--pdf']:group.add_argument(flag)
    p.add_argument('--output-dir');p.add_argument('--original');p.add_argument('--main')
    p.add_argument('--config');p.add_argument('--provider',choices=['cpa','deepseek','ollama'],default='cpa')
    p.add_argument('--workers',type=int,default=4);p.add_argument('--compile-timeout',type=int,default=180)
    p.add_argument('--prompt',choices=['zotero_default','cs_ai_specialized','math_formula_preservation'],default='zotero_default')
    p.add_argument('--no-fallback',action='store_true');p.add_argument('--doctor',action='store_true')
    args=p.parse_args()
    if args.doctor:return 0 if doctor() else 2
    target=args.input or args.arxiv or args.dir or args.pdf
    if not target:p.print_help();return 2
    if not 1<=args.workers<=16:p.error('--workers must be 1..16')
    try:
        ok=auto_translate_paper(target,args.output_dir,args.provider,args.workers,load_config(args.config),args.original,args.main,args.no_fallback,args.prompt,args.compile_timeout)
        return 0 if ok else 2
    except Exception as e:print('Error:',str(e));return 2


if __name__=='__main__':sys.exit(main())
