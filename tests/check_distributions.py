"""Validate release contents and metadata without executing a translation."""
import email
import json
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

root = Path(__file__).resolve().parents[1]
dist = Path(sys.argv[1])
version = (root / 'VERSION').read_text(encoding='utf-8').strip()
wheel, = dist.glob('*.whl')
sdist, = dist.glob('*.tar.gz')
for path in (wheel, sdist):
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            files = {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}
    else:
        with tarfile.open(path) as archive:
            files = {n.name: archive.extractfile(n).read() for n in archive if n.isfile()}
    for name, content in files.items():
        parts = PurePosixPath(name).parts
        assert not any(p in {'.env', '.translation', '.build', '.venv', 'venv', '__pycache__', 'config.local.json', 'config.yaml', 'config.local.yaml'} or p.startswith('.env.') for p in parts), name
        assert not name.endswith(('.pyc', '.log', '.zip', '.bundle')), name
        assert (b'PACKAGING_PRIVATE_' + b'SENTINEL') not in content, name
    assert any(n.endswith('/prompts/zotero_default.txt') for n in files)
    assert any(n.endswith('/VERSION') for n in files)
    assert any(n.endswith('/references/visual_review.md') for n in files)
    assert any(n.endswith('/scripts/delivery.py') for n in files)
    if path.suffix == '.whl':
        metadata, = [v for n,v in files.items() if n.endswith('.dist-info/METADATA')]
        message = email.message_from_bytes(metadata)
        assert message['Version'] == version
        required = message.get_all('Requires-Dist')
        assert any(v == 'PyMuPDF==1.28.2' for v in required), required
        assert any(v.startswith('uv>=') and 'extra == "pdf"' in v for v in required), required
print(json.dumps({'version':version,'wheel_and_sdist':'passed','private_files':'absent'}))
