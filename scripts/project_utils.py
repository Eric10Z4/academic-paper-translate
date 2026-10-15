from __future__ import annotations
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

IGNORE_DIRS={'.git','.venv','venv','__pycache__','.translation','.build','node_modules'}
GENERATED_EXTS={'.aux','.blg','.log','.out','.toc','.lof','.lot','.fls','.fdb_latexmk','.xdv','.bcf','.nav','.snm','.vrb'}


def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive random temporary paths cannot follow an attacker/stale symlink.
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    tmp=Path(name)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def read_utf8(path):return Path(path).read_bytes().decode('utf-8')


def project_files(root,exclude=()):
    root=Path(root).resolve();exclude=[Path(p).resolve() for p in exclude]
    for folder,dirs,files in os.walk(root,followlinks=False):
        folder=Path(folder)
        dirs[:]=[d for d in sorted(dirs) if d not in IGNORE_DIRS and not (folder/d).is_symlink() and not any((folder/d).resolve().is_relative_to(e) for e in exclude)]
        for name in sorted(files):
            p=folder/name
            if p.is_symlink():raise ValueError('Symbolic link in project: '+str(p))
            if any(p.resolve().is_relative_to(e) for e in exclude):continue
            if p.suffix.lower() in GENERATED_EXTS or name.endswith(('.synctex.gz','.run.xml','.pyc')):continue
            yield p


def copy_project(source,destination,exclude=()):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if destination==source:raise ValueError('Working copy must differ from source')
    files=list(project_files(source,[*exclude,destination]))
    destination.mkdir(parents=True,exist_ok=True)
    for path in files:
        target=destination/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
    return destination


def pdf_info(path):
    import pymupdf
    with pymupdf.open(str(path)) as doc:
        if doc.is_encrypted or doc.page_count<1:raise ValueError('PDF is empty or encrypted')
        return {'pages':len(doc),'bytes':Path(path).stat().st_size,'sha256':sha256(path),'page_sizes':[[round(p.rect.width,3),round(p.rect.height,3)] for p in doc]}


def safe_extract_tar(archive,destination,max_files=10000,max_bytes=512*1024*1024):
    import tarfile
    root=Path(destination).resolve();root.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive,'r:*') as tar:
        members=[];total=0
        for m in tar:
            members.append(m);total+=m.size
            if len(members)>max_files or total>max_bytes:raise ValueError('Source archive exceeds limits')
            name=m.name.replace('\\','/')
            dest=(root/name).resolve()
            if not dest.is_relative_to(root) or ':' in name or m.issym() or m.islnk() or not(m.isfile() or m.isdir()):
                raise ValueError('Unsafe archive member')
        tar.extractall(root,members=members,filter='data')
