"""Finish a visually reviewed delivery; remove only verified run-owned files."""
from __future__ import annotations
import json
import os
import re
import shutil
from pathlib import Path
from .project_utils import atomic_json, pdf_info, sha256

PDFS = ('original.pdf', 'chinese_mono.pdf', 'bilingual_dual.pdf')
ARCHIVES = ('chinese_source.zip', 'chinese_source_uncompiled.zip')
CHECKS = ('inline_fractions', 'display_math', 'algorithm_structure', 'clipping')


def _reject_links(path):
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Cleanup refuses symbolic links or junctions: ' + str(path))


def _checked_target(root, path):
    if not path.is_relative_to(root):
        raise ValueError('Evidence destination escapes its directory')
    for item in [path, *path.parents]:
        _reject_links(item)
        if item==root:break
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Evidence destination escapes its directory')
    if path.is_file() and path.stat().st_nlink>1:
        raise ValueError('Evidence destination has multiple hard links')
    return path


def _review(review, manifest, final):
    if not isinstance(review, dict) or not str(review.get('reviewer', '')).strip():
        raise ValueError('A visual review with reviewer and PDF hashes is required')
    if not str(review.get('notes', '')).strip():
        raise ValueError('Visual review must describe the observed result')
    if any(review.get('checks', {}).get(name) != 'passed' for name in CHECKS):
        raise ValueError('Fractions, display math, algorithms and clipping must pass visual review')
    for name in PDFS:
        expected = manifest.get('artifacts', {}).get(name, {}).get('sha256')
        if not expected or review.get('artifacts', {}).get(name) != expected:
            raise ValueError('Visual review is missing or refers to a different PDF: ' + name)
        _reject_links(final/name)
        if sha256(final/name) != expected:
            raise ValueError('PDF changed after translation/review: ' + name)
    pages = pdf_info(final/'chinese_mono.pdf')['pages']
    if review.get('reviewed_pages') != list(range(1, pages+1)):
        raise ValueError('Review every Chinese page and record 1-based pages in order')


def finalize_delivery(output_dir, review_path, keep_source=False):
    """review_path records actual rendered-page inspection, never model self-certification.

    Takes the same output lock as translation. A failed/incomplete run is retained.
    Does not search parent directories or delete user inputs by extension.
    """
    final = Path(output_dir).expanduser().absolute()
    _reject_links(final)
    final = final.resolve()
    private = final/'.translation'
    _reject_links(private)
    private.mkdir(exist_ok=True)
    lock = private/'active.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('Translation is still active; do not clean its workspace') from None
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({'pid':os.getpid(), 'operation':'finalize'}, f)
        manifest_path = final/'translation_manifest.json'
        _reject_links(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('status') not in {'complete_native', 'complete_fallback', 'review_required'}:
            raise ValueError('Failed or running translations must retain diagnostic sources')
        if manifest.get('mode') not in {'latex_native', 'pdf_fallback'}:
            raise ValueError('Unknown translation mode')
        review = json.loads(Path(review_path).read_text(encoding='utf-8'))
        _review(review, manifest, final)
        runs = private/'runs'
        _reject_links(runs)
        run = Path(manifest.get('run_dir', '')).absolute()
        _reject_links(run)
        if run.parent.resolve() != runs.resolve() or not re.fullmatch(r'[0-9a-f]{32}', run.name):
            raise ValueError('Run path is not an owned output workspace')
        # Windows manifests may use an 8.3 alias while final is resolved to its
        # long name. Use the verified owner directory before any deletion or
        # lexical relative-path operation; otherwise recording cleanup can fail.
        run = runs/run.name
        run_relative = run.relative_to(final)
        # No mutation until the entire deletion set and the PDFs have been checked.
        if run.exists():
            for folder, dirs, files in os.walk(run, followlinks=False):
                for name in dirs + files:
                    item = Path(folder)/name
                    _reject_links(item)
                    if not item.resolve().is_relative_to(run.resolve()):
                        raise ValueError('Cleanup path escapes the run workspace')
        archives = []
        for name in ARCHIVES:
            path = final/name
            if keep_source or not path.exists():
                continue
            _reject_links(path)
            expected = (manifest.get('artifacts', {}).get(name, {}).get('sha256') or
                        manifest.get('prior_source_archives', {}).get(name, {}).get('sha256'))
            if not expected or sha256(path) != expected:
                raise ValueError('Untracked or changed source archive; retain it: ' + name)
            archives.append(path)
        # Preserve small diagnostic records before removing bulky source/build copies.
        evidence = private/'evidence'/run.name
        _reject_links(private/'evidence')
        _reject_links(evidence)
        evidence.mkdir(parents=True, exist_ok=True)
        evidence_files=[]
        if run.exists():
            for item in run.rglob('*'):
                if item.is_file() and item.name in {'compile_report.json', 'fallback_report.json', 'source_acquisition.json', 'engine.log'}:
                    evidence_files.append((item,_checked_target(evidence,evidence/item.relative_to(run))))
        _reject_links(final/'visual_review.json')
        for item,target in evidence_files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        atomic_json(final/'visual_review.json', review)
        removed = []
        for archive in archives:
            archive.unlink()
            manifest['artifacts'].pop(archive.name, None)
            manifest.get('prior_source_archives',{}).pop(archive.name,None)
            removed.append(archive.name)
        if run.exists():
            # Resolved absolute target was checked above; never delete arbitrary .tex/ZIPs.
            shutil.rmtree(run)
            removed.append(str(run_relative))
        manifest['visual_review'] = {'status':'passed', 'record':'visual_review.json',
                                   'reviewer':review['reviewer'], 'pages':review['reviewed_pages']}
        manifest['status'] = 'complete_native' if manifest['mode']=='latex_native' else 'complete_fallback'
        manifest['cleanup'] = {'status':'complete', 'removed':removed,
                               'source_archive_retained':keep_source,
                               'evidence_dir':str(evidence.relative_to(final))}
        atomic_json(manifest_path, manifest)
        return manifest
    finally:
        lock.unlink(missing_ok=True)
