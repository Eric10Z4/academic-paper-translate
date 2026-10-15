"""Smoke-check an installed wheel from outside the source tree; no API calls."""
import importlib.metadata
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

from academic_paper_translate.scripts import zotero_translate as z
from academic_paper_translate.scripts import pdf_runner
from academic_paper_translate.scripts import delivery
from academic_paper_translate.scripts.project_utils import pdf_info

version = (z.ROOT / 'VERSION').read_text(encoding='utf-8').strip()
assert version == importlib.metadata.version('academic-paper-translate')
assert Path(sys.prefix).resolve() in z.ROOT.resolve().parents
assert 'scripts' not in sys.modules and 'adapters' not in sys.modules
assert pdf_runner.PDF2ZH_VERSION == '2.9.0'
assert pdf_runner.BABELDOC_VERSION == '0.6.2'
assert (z.ROOT/'references/visual_review.md').is_file()
for prompt in ('zotero_default', 'cs_ai_specialized', 'math_formula_preservation'):
    assert '__SOURCE_TEXT__' in (z.ROOT / 'prompts' / (prompt + '.txt')).read_text(encoding='utf-8')
assert not (z.ROOT / 'config.local.json').exists()
assert json.loads((z.ROOT / 'config.example.json').read_text(encoding='utf-8'))['providers']

with tempfile.TemporaryDirectory() as directory:
    cwd = Path(directory)
    config = cwd / 'provider.json'
    config.write_text(json.dumps({'providers': {'cpa': {'base_url': 'http://127.0.0.1:1/v1', 'model': 'test-model'}}}), encoding='utf-8')
    assert z.load_config(config)['providers']['cpa']['model'] == 'test-model'
    command = Path(sysconfig.get_path('scripts')) / ('paper-translate.exe' if os.name == 'nt' else 'paper-translate')
    help_result = subprocess.run([str(command), '--help'], cwd=cwd, capture_output=True, text=True)
    assert help_result.returncode == 0, help_result.stderr
    assert '--output-dir' in help_result.stdout and '--output-zip' not in help_result.stdout
    assert '--finalize' in help_result.stdout and '--visual-review' in help_result.stdout
    doctor = subprocess.run([str(command), '--doctor'], cwd=cwd, capture_output=True, text=True)
    checks = json.loads(doctor.stdout)
    assert checks['pymupdf']
    assert doctor.returncode == (0 if checks['xelatex'] else 2)
    # Exercise finalization through the installed CLI, not the source checkout.
    # These synthetic PDFs test packaging/imports only; no visual-quality claim.
    import pymupdf
    output=cwd/'delivery';run=output/'.translation/runs'/('a'*32)
    run.mkdir(parents=True)
    (run/'generated.tex').write_text('temporary generated source',encoding='utf-8')
    artifacts={}
    for name in delivery.PDFS:
        with pymupdf.open() as document:
            page=document.new_page();page.insert_text((72,72),'Packaging test')
            document.save(str(output/name))
        artifacts[name]=pdf_info(output/name)
    manifest={'status':'complete_native','mode':'latex_native','run_dir':str(run),'artifacts':artifacts}
    (output/'translation_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    review={'reviewer':'synthetic packaging fixture','notes':'Tests installed CLI imports and cleanup only.',
            'reviewed_pages':[1],'checks':dict.fromkeys(delivery.CHECKS,'passed'),
            'artifacts':{name:info['sha256'] for name,info in artifacts.items()}}
    review_path=cwd/'synthetic_review.json';review_path.write_text(json.dumps(review),encoding='utf-8')
    finalized=subprocess.run([str(command),'--finalize',str(output),'--visual-review',str(review_path)],
                             cwd=cwd,capture_output=True,text=True)
    assert finalized.returncode==0,(finalized.stdout,finalized.stderr)
    assert not run.exists()
    assert json.loads((output/'translation_manifest.json').read_text(encoding='utf-8'))['cleanup']['status']=='complete'
    assert all(pdf_info(output/name)['sha256']==info['sha256'] for name,info in artifacts.items())
print(json.dumps({'installed_version': version, 'resources': 'passed', 'isolated_cli': 'passed'}))
