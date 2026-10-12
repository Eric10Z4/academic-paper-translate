"""Fresh, checked XeLaTeX builds and lossless page composition."""
from __future__ import annotations
import hashlib
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from .project_utils import atomic_json, copy_project, pdf_info, project_files, read_utf8

BEGIN='% HERMES-TRANSLATE CHINESE BEGIN'
END='% HERMES-TRANSLATE CHINESE END'
FONT_BEGIN='% HERMES-TRANSLATE LEGACY FONT BEGIN'
FONT_END='% HERMES-TRANSLATE LEGACY FONT END'


def without_comments(text):
    # Preserve offsets for injection and distinguish escaped percent from a
    # comment after an escaped backslash.
    chars=list(text);i=0
    while i<len(text):
        if text[i]=='\\':i+=2;continue
        if text[i]=='%':
            end=i
            while end<len(text) and text[end] not in '\r\n':end+=1
            chars[i:end]=' '*(end-i);i=end
        else:i+=1
    return ''.join(chars)


def find_main_tex(project_dir):
    root=Path(project_dir).resolve();candidates=[]
    for p in project_files(root):
        if p.suffix.lower()!='.tex':continue
        try:text=without_comments(read_utf8(p))
        except UnicodeDecodeError:continue
        if re.search(r'\\documentclass(?:\s*\[[^]]*\])?\s*\{',text) and re.search(r'\\begin\s*\{document\}',text):
            score=(100 if p.parent==root else 0)+{'main.tex':30,'paper.tex':20,'ms.tex':20}.get(p.name.lower(),0)
            candidates.append((score,str(p)))
    candidates.sort(reverse=True)
    if not candidates:return None
    if len(candidates)>1 and candidates[0][0]==candidates[1][0]:raise ValueError('Ambiguous TeX entry; specify --main')
    return candidates[0][1]


def inject_chinese_support(tex_path,fallback_xecjk=False):
    path=Path(tex_path);content=read_utf8(path)
    content=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END)+r'\r?\n?', '', content, flags=re.S)
    active=without_comments(content)
    # Existing user-supplied Chinese support is never silently rewritten.
    if re.search(r'\\(?:usepackage|RequirePackage)(?:\s*\[[^]]*\])?\s*\{[^}]*\b(?:ctex|xeCJK)\b',active) or re.search(r'\\documentclass(?:\[[^]]*\])?\s*\{ctex',active):
        return False
    from .latex_syntax import arguments
    m=re.search(r'\\documentclass\b',active)
    if not m:raise ValueError('No documentclass')
    _,pos=arguments(content,m.end(),limit=1)
    package=r'\usepackage{xeCJK}' if fallback_xecjk else r'\usepackage[UTF8,scheme=plain]{ctex}'
    fonts=''
    if fallback_xecjk and os.name=='nt':
        fonts='\n\\setCJKmainfont[BoldFont=SimHei,ItalicFont=KaiTi]{SimSun}\n\\setCJKsansfont{SimHei}\n\\setCJKmonofont{FangSong}'
    injection='\n'+BEGIN+'\n'+package+fonts+'\n\\tolerance=1000\n\\emergencystretch=3em\n'+END+'\n'
    path.write_bytes((content[:pos]+injection+content[pos:]).encode('utf-8'))
    return True


def inject_legacy_font_support(tex_path,families):
    """Repair only families that XeTeX actually reported as undefined in TU.

    Insert after the template's font defaults, before document initialization.
    Never rewrite a template or switch an already functioning font family.
    """
    path=Path(tex_path);content=read_utf8(path)
    content=re.sub(re.escape(FONT_BEGIN)+r'.*?'+re.escape(FONT_END)+r'\r?\n?', '',content,flags=re.S)
    active=without_comments(content);match=re.search(r'\\begin\s*\{document\}',active)
    if not match:raise ValueError('No document environment for font compatibility')
    names={'ptm':('setmainfont','Times New Roman' if os.name=='nt' else 'TeX Gyre Termes'),
           'phv':('setsansfont','Arial' if os.name=='nt' else 'TeX Gyre Heros'),
           'pcr':('setmonofont','Courier New' if os.name=='nt' else 'TeX Gyre Cursor')}
    lines=[FONT_BEGIN,r'\usepackage{fontspec}']
    lines.extend('\\'+names[f][0]+'{'+names[f][1]+'}' for f in sorted(families))
    lines.append(FONT_END)
    content=content[:match.start()]+'\n'.join(lines)+'\n'+content[match.start():]
    path.write_bytes(content.encode('utf-8'))


def _run(cmd,cwd,timeout,env,logfile):
    try:
        p=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=timeout)
        raw=(p.stdout or b'')+b'\n'+(p.stderr or b'')
        Path(logfile).write_bytes(raw)
        return p.returncode,raw.decode('utf-8',errors='replace')
    except subprocess.TimeoutExpired as e:
        Path(logfile).write_bytes((e.stdout or b'')+b'\nTIMEOUT\n'+(e.stderr or b''))
        return 124,'Compiler timeout'
    except OSError as e:
        Path(logfile).write_text(str(e),encoding='utf-8')
        return 127,str(e)


def compile_latex_project(project_dir,main_tex_path=None,timeout=180,chinese=True,max_passes=5):
    root=Path(project_dir).resolve()
    try:
        main=Path(main_tex_path or find_main_tex(root)).resolve()
        if not main.is_relative_to(root):raise ValueError('Entry outside source root')
    except (TypeError,ValueError) as e:return False,None,str(e)
    if not shutil.which('xelatex'):return False,None,'XeLaTeX is not installed or not on PATH'
    build=root/'.build'/uuid.uuid4().hex
    report={'attempts':[],'success':False}
    attempts=[(mode,()) for mode in (['ctex','xecjk'] if chinese else ['original'])]
    for attempt_index,(base_mode,legacy_families) in enumerate(attempts):
        mode=base_mode+('_legacyfonts' if legacy_families else '')
        attempt=build/mode;copy_project(root,attempt)
        entry=attempt/main.relative_to(root);cwd=entry.parent;stem=entry.stem
        inject=False
        if chinese:inject=inject_chinese_support(entry,fallback_xecjk=base_mode=='xecjk')
        if legacy_families:inject_legacy_font_support(entry,legacy_families)
        expected=cwd/(stem+'.pdf')
        if expected.exists():expected.unlink()
        env=os.environ.copy()
        for key in ['TEXINPUTS','BIBINPUTS','BSTINPUTS']:
            env[key]=str(attempt).replace('\\','/')+'//'+os.pathsep+env.get(key,'')
        cmd=['xelatex','--disable-installer','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error',entry.name]
        attempt_log={'mode':mode,'passes':[],'injected':inject,'legacy_font_families':list(legacy_families)};report['attempts'].append(attempt_log)
        failed=False;previous=None;converged=False
        for n in range(1,max_passes+1):
            rc,stdout=_run(cmd,cwd,timeout,env,cwd/f'hermes-pass-{n}.txt')
            attempt_log['passes'].append({'engine':'xelatex','number':n,'returncode':rc})
            log=(cwd/(stem+'.log')).read_bytes().decode('utf-8',errors='replace') if (cwd/(stem+'.log')).exists() else stdout
            if rc!=0:
                attempt_log['error']=log[-6000:];failed=True;break
            missing_legacy=sorted(set(re.findall(r"Font shape [`']TU/(ptm|phv|pcr)/",log)))
            if missing_legacy and not legacy_families:
                attempts.insert(attempt_index+1,(base_mode,tuple(missing_legacy)))
                attempt_log['error']='Legacy font encoding incompatible; retry with an explicit Unicode font for '+','.join(missing_legacy)
                failed=True;break
            if n==1:
                aux_path=cwd/(stem+'.aux');aux=aux_path.read_bytes().decode('utf-8',errors='replace') if aux_path.exists() else ''
                engine=None
                if (cwd/(stem+'.bcf')).exists():engine='biber'
                elif re.search(r'\\bibdata\{',aux):
                    # A source-only .bbl is authoritative when no .bib was supplied.
                    if list(attempt.rglob('*.bib')):engine='bibtex'
                    elif not (cwd/(stem+'.bbl')).exists():
                        failed=True;attempt_log['error']='Bibliography requested but neither .bib nor .bbl exists';break
                if engine:
                    rc,biblog=_run([engine,stem],cwd,timeout,env,cwd/'hermes-bibliography.txt')
                    attempt_log['passes'].append({'engine':engine,'returncode':rc})
                    if rc!=0:failed=True;attempt_log['error']=biblog[-4000:];break
            signature=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(cwd.rglob('*.aux')))).hexdigest()
            pending=bool(re.search(r'There were undefined|(?:Citation|Reference)[^\n]*undefined|Label\(s\) may have changed|Rerun to get|Please \(re\)run (?:Biber|BibTeX)',log,re.I))
            if n>=3 and previous==signature and not pending:converged=True;break
            previous=signature
        if failed:continue
        if not converged:attempt_log['error']='Cross references or bibliography did not converge';continue
        if re.search(r'Missing character:|Fatal error|^! ',log,re.M):attempt_log['error']='Missing glyphs or fatal TeX error';continue
        try:info=pdf_info(expected)
        except Exception as e:attempt_log['error']='Invalid newly built PDF: '+str(e);continue
        warnings=re.findall(r'Overfull \\[hv]box[^\n]*',log)
        warnings.extend(re.findall(r'LaTeX Font Warning:[^\n]*',log))
        attempt_log.update({'pdf':info,'layout_warnings':warnings})
        report.update({'success':True,'selected_mode':mode,'pdf':str(expected),'layout_warnings':warnings})
        atomic_json(build/'compile_report.json',report)
        if chinese and (inject or legacy_families):main.write_bytes(entry.read_bytes())
        return True,str(expected),json_summary(report,build/'compile_report.json')
    atomic_json(build/'compile_report.json',report)
    return False,None,json_summary(report,build/'compile_report.json')


def json_summary(report,path):
    import json
    return json.dumps({'success':report['success'],'report':str(path),'layout_warnings':report.get('layout_warnings',[]),'errors':[a.get('error','')[-2000:] for a in report['attempts'] if a.get('error')]},ensure_ascii=False)


def make_side_by_side_dual_pdf(original_pdf_path,mono_pdf_path,output_dual_pdf_path):
    import pymupdf as fitz
    output=Path(output_dual_pdf_path);output.parent.mkdir(parents=True,exist_ok=True)
    with fitz.open(str(original_pdf_path)) as orig,fitz.open(str(mono_pdf_path)) as mono,fitz.open() as out:
        if not len(orig) or not len(mono):raise ValueError('Cannot pair an empty PDF')
        count=max(len(orig),len(mono))
        geometry=[]
        for i in range(count):
            left=orig[i] if i<len(orig) else None;right=mono[i] if i<len(mono) else None
            wl=left.rect.width if left else orig[-1].rect.width
            wr=right.rect.width if right else mono[-1].rect.width
            height=max(left.rect.height if left else 0,right.rect.height if right else 0)
            page=out.new_page(width=wl+wr,height=height);geometry.append(wl)
            for source,srcpage,x in [(orig,left,0),(mono,right,wl)]:
                if srcpage is None:
                    page.insert_text((x+24,40),'No corresponding page in this version.',fontsize=10);continue
                page.show_pdf_page(fitz.Rect(x,0,x+srcpage.rect.width,srcpage.rect.height),source,i)
        # Insert links only after all destinations exist.
        for i in range(count):
            for source,x in [(orig,0),(mono,geometry[i])]:
                if i>=len(source):continue
                for link in source[i].get_links():
                    if link['kind'] not in {fitz.LINK_URI,fitz.LINK_GOTO}:continue
                    obj={k:v for k,v in link.items() if k in {'kind','from','uri','page','to','zoom'}}
                    rect=fitz.Rect(link['from']);rect.x0+=x;rect.x1+=x;obj['from']=rect
                    if link['kind']==fitz.LINK_GOTO:
                        target=link.get('page',-1)
                        if not 0<=target<count:continue
                        point=fitz.Point(link.get('to',(0,0)))
                        if source is mono:point.x+=geometry[target]
                        obj['to']=point
                    out[i].insert_link(obj)
        toc=[]
        for label,source in [('Original',orig),('Chinese',mono)]:
            toc.append([1,label,1]);toc.extend([[level+1,title,p] for level,title,p in source.get_toc()])
        out.set_toc(toc)
        out.set_metadata({'title':'English and Chinese page comparison','subject':'Pages paired by index; reflow may change correspondence.'})
        temp=output.with_name(output.stem+'.tmp.pdf');out.save(str(temp),deflate=True)
    os.replace(temp,output)
    if pdf_info(output)['pages']!=count:raise ValueError('Dual PDF lost pages')
    return True


def pack_source_zip(project_dir,output_zip_path):
    root=Path(project_dir).resolve();output=Path(output_zip_path).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    try:main=find_main_tex(root)
    except ValueError:main=None
    generated_pdf=Path(main).with_suffix('.pdf') if main else None
    paths=[p for p in project_files(root,[output]) if p!=generated_pdf and p.name not in {'original.pdf','chinese_mono.pdf','bilingual_dual.pdf'} and not p.name.startswith('hermes-pass-')]
    temp=output.with_name(output.name+'.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p==temp:continue
            z.write(p,p.relative_to(root).as_posix())
    with zipfile.ZipFile(temp) as z:
        if z.testzip():raise ValueError('Corrupt source archive')
    os.replace(temp,output)
    return True
