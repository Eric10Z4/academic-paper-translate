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

version = (z.ROOT / 'VERSION').read_text(encoding='utf-8').strip()
assert version == importlib.metadata.version('academic-paper-translate')
assert Path(sys.prefix).resolve() in z.ROOT.resolve().parents
assert 'scripts' not in sys.modules and 'adapters' not in sys.modules
assert pdf_runner.PDF2ZH_VERSION == '2.9.0'
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
    doctor = subprocess.run([str(command), '--doctor'], cwd=cwd, capture_output=True, text=True)
    checks = json.loads(doctor.stdout)
    assert checks['pymupdf']
    assert doctor.returncode == (0 if checks['xelatex'] else 2)
print(json.dumps({'installed_version': version, 'resources': 'passed', 'isolated_cli': 'passed'}))
