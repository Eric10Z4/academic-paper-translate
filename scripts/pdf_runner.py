"""Pinned, bounded PDF fallback. Secrets are passed only in child environment."""
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from .latex_compiler import make_side_by_side_dual_pdf
from .project_utils import atomic_json,pdf_info

PDF2ZH_VERSION='2.9.0'


def run_pdf_translation(pdf_path,output_dir,dual=True,mono=True,qps=4,custom_prompt=None,config=None,provider='cpa'):
    from .zotero_translate import get_adapter,load_config
    if not mono or not dual:raise ValueError('Standard delivery requires both mono and dual PDFs')
    config=load_config() if config is None else config
    settings=config.get('fallback',{})
    adapter=get_adapter(provider,config)
    root=Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=True)
    scratch=root/('pdf_fallback_'+uuid.uuid4().hex);scratch.mkdir()
    cache=settings.get('uv_cache_dir',str(Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'hermes/cache/academic-paper-translate/uv'))
    cmd=['uv.exe' if os.name=='nt' else 'uv','tool','run','--cache-dir',cache,'--with','bitstring<5.0.0','--from','pdf2zh-next=='+PDF2ZH_VERSION,'pdf2zh_next',str(Path(pdf_path).resolve()),
         '--openaicompatible','--openai-compatible-base-url',adapter.base_url,'--openai-compatible-model',adapter.model,
         '--openai-compatible-timeout',str(adapter.timeout),'--no-auto-extract-glossary','--figure-table-protection-threshold','0.1',
         '--watermark-output-mode','no_watermark','--qps',str(qps),'--lang-in','en','--lang-out','zh-CN','--no-dual',
         '--custom-system-prompt',custom_prompt or 'Translate all academic prose faithfully into Simplified Chinese. Do not summarize, explain or change formulas, data, citations or names of methods. Output only the translation.',
         '--output',str(scratch)]
    env=os.environ.copy();env['PDF2ZH_OPENAI_COMPATIBLE_API_KEY']=adapter.api_key
    env['PDF2ZH_TRANSLATE_TABLE_TEXT']='false'
    env['PDF2ZH_DISABLE_CONFIG_AUTO_SAVE']='true'
    env['NO_PROXY']=settings.get('no_proxy','127.0.0.1,localhost');env['no_proxy']=env['NO_PROXY']
    report={'engine':'pdf2zh-next','version':PDF2ZH_VERSION,'success':False,'scratch':str(scratch)}
    logfile=scratch/'engine.log'
    try:
        with open(logfile,'wb') as log:
            proc=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=settings.get('timeout',1200))
        report['returncode']=proc.returncode
        if proc.returncode:raise RuntimeError('PDF fallback engine returned a nonzero exit code; see engine.log')
        candidates=[p for p in scratch.rglob('*.pdf') if 'mono' in p.stem.lower()]
        if len(candidates)!=1:raise RuntimeError('Expected exactly one new monolingual PDF')
        translated=candidates[0]
        report['mono']=pdf_info(translated)
        if report['mono']['pages']!=pdf_info(pdf_path)['pages']:raise RuntimeError('Fallback changed page count unexpectedly')
        shutil.copy2(translated,root/'chinese_mono.pdf')
        original=root/'original.pdf'
        if Path(pdf_path).resolve()!=original:shutil.copy2(pdf_path,original)
        make_side_by_side_dual_pdf(original,root/'chinese_mono.pdf',root/'bilingual_dual.pdf')
        pdf_info(root/'bilingual_dual.pdf');report['success']=True
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as e:
        report['error']=str(e)
    finally:
        # The engine may include configuration in logs. Never retain a plaintext key.
        if logfile.exists() and adapter.api_key:
            raw=logfile.read_bytes().replace(adapter.api_key.encode(),b'[REDACTED]');logfile.write_bytes(raw)
        atomic_json(root/'fallback_report.json',report)
    return report['success']
