"""Pinned, bounded PDF fallback. Secrets are passed only in child environment."""
import os
import math
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from .latex_compiler import make_side_by_side_dual_pdf
from .project_utils import atomic_json,pdf_info

PDF2ZH_VERSION='2.9.0'
BABELDOC_VERSION='0.6.2'


def _layout_options(settings):
    """Preserve unassigned strokes; short-line splitting needs paper-specific review.

    These options do not prove that a fraction is grouped correctly. In particular,
    retaining a fraction bar cannot repair separately displaced numerator glyphs.
    """
    preserve = settings.get('preserve_unassigned_lines', True)
    split = settings.get('split_short_lines', False)
    if not isinstance(preserve, bool) or not isinstance(split, bool):
        raise ValueError('PDF layout switches must be JSON booleans')
    args = ['--no-remove-non-formula-lines'] if preserve else []
    options = {'preserve_unassigned_lines': preserve, 'split_short_lines': split}
    if split:
        factor = float(settings.get('short_line_split_factor', 0.8))
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError('short_line_split_factor must be a positive finite number')
        args += ['--split-short-lines', '--short-line-split-factor', str(factor)]
        options['short_line_split_factor'] = factor
    return args, options


def inspect_pdf_formula_risks(pdf_path):
    """List candidate pages for visual review, never certify formula preservation.

    Fraction strokes are PDF graphics, separate from their numerator/denominator
    text. This deliberately limited heuristic finds short horizontal strokes or
    inline image masks with characters on both sides. It misses full image
    formulas and some fonts/layouts.
    Algorithm headings are review hints only; no guessed rectangle is overwritten.
    """
    import pymupdf as fitz
    fraction_pages = []
    algorithm_pages = []
    fraction_counts = {}
    image_mask_pages = []
    with fitz.open(pdf_path) as document:
        for number, page in enumerate(document, 1):
            text = page.get_text('text')
            if re.search(r'^\s*(?:Algorithm\s+\d+|算法\s*\d+)', text, re.I | re.M):
                algorithm_pages.append(number)
            characters = [
                (char['c'], fitz.Rect(char['bbox']))
                for block in page.get_text('rawdict')['blocks'] if block.get('type') == 0
                for line in block['lines'] for span in line['spans']
                for char in span['chars'] if char['c'].strip()
            ]
            strokes = set()
            stroke_candidates = []
            for drawing in page.get_drawings():
                for item in drawing['items']:
                    if item[0] == 'l':
                        a, b = item[1:3]
                        if abs(a.y - b.y) > 0.5:
                            continue
                        x0, x1, y = min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2
                    elif item[0] == 're':
                        rect = item[1]
                        if rect.height > 1.5:
                            continue
                        x0, x1, y = rect.x0, rect.x1, (rect.y0 + rect.y1) / 2
                    else:
                        continue
                    stroke_candidates.append((x0, x1, y, False))
            # PostScript-derived PDFs can encode fraction bars as inline masks.
            # get_images() and get_drawings() both miss these; SCORE is one example.
            for kind, bbox in page.get_bboxlog():
                if kind != 'fill-imgmask':
                    continue
                rect = fitz.Rect(bbox)
                if rect.height <= 1.5:
                    stroke_candidates.append((rect.x0, rect.x1, (rect.y0 + rect.y1) / 2, True))
            has_fraction_mask = False
            for x0, x1, y, image_mask in stroke_candidates:
                if not 3 <= x1 - x0 <= 150:
                    continue
                near = [box for _, box in characters
                        if x0 - 1 <= (box.x0 + box.x1) / 2 <= x1 + 1]
                above = any(y - 14 <= box.y1 <= y + 2 and
                            (box.y0 + box.y1) / 2 < y for box in near)
                below = any(y - 2 <= box.y0 <= y + 14 and
                            (box.y0 + box.y1) / 2 > y for box in near)
                if above and below:
                    strokes.add((round(x0, 2), round(x1, 2), round(y, 2)))
                    has_fraction_mask |= image_mask
            if has_fraction_mask:
                image_mask_pages.append(number)
            if strokes:
                fraction_pages.append(number)
                fraction_counts[str(number)] = len(strokes)
    return {
        'status': 'completed',
        'method': 'source_geometry_review_hints',
        'coverage': 'heuristic_incomplete',
        'fraction_candidate_pages': fraction_pages,
        'fraction_candidate_counts': fraction_counts,
        'inline_image_mask_fraction_pages': image_mask_pages,
        'algorithm_heading_pages': algorithm_pages,
        'priority_review_pages': sorted(set(fraction_pages + algorithm_pages)),
        'limitations': 'Hints only. Images, unusual fonts and unlabelled algorithms can be missed; review all translated pages.',
    }


def run_pdf_translation(pdf_path,output_dir,dual=True,mono=True,qps=4,custom_prompt=None,config=None,provider='cpa'):
    from .zotero_translate import get_adapter,load_config
    if not mono or not dual:raise ValueError('Standard delivery requires both mono and dual PDFs')
    config=load_config() if config is None else config
    settings=config.get('fallback',{})
    layout_args, layout_settings = _layout_options(settings)
    adapter=get_adapter(provider,config)
    root=Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=True)
    scratch=root/('pdf_fallback_'+uuid.uuid4().hex);scratch.mkdir()
    cache=settings.get('uv_cache_dir',str(Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'hermes/cache/academic-paper-translate/uv'))
    cmd=['uv.exe' if os.name=='nt' else 'uv','tool','run','--cache-dir',cache,'--with','bitstring<5.0.0','--with','babeldoc=='+BABELDOC_VERSION,'--from','pdf2zh-next=='+PDF2ZH_VERSION,'pdf2zh_next',str(Path(pdf_path).resolve()),
         '--openaicompatible','--openai-compatible-base-url',adapter.base_url,'--openai-compatible-model',adapter.model,
         '--openai-compatible-timeout',str(adapter.timeout),'--no-auto-extract-glossary','--figure-table-protection-threshold','0.1',
         '--watermark-output-mode','no_watermark','--qps',str(qps),'--lang-in','en','--lang-out','zh-CN','--no-dual',
         '--custom-system-prompt',custom_prompt or 'Translate all academic prose faithfully into Simplified Chinese. Do not summarize, explain or change formulas, data, citations or names of methods. Output only the translation.',
         '--output',str(scratch)]
    cmd += layout_args
    env=os.environ.copy();env['PDF2ZH_OPENAI_COMPATIBLE_API_KEY']=adapter.api_key
    env['PDF2ZH_TRANSLATE_TABLE_TEXT']='false'
    env['PDF2ZH_DISABLE_CONFIG_AUTO_SAVE']='true'
    env['NO_PROXY']=settings.get('no_proxy','127.0.0.1,localhost');env['no_proxy']=env['NO_PROXY']
    report={'engine':'pdf2zh-next','version':PDF2ZH_VERSION,'babeldoc_version':BABELDOC_VERSION,
            'success':False,'scratch':str(scratch),'layout_options':layout_settings,
            'quality_status':'not_validated',
            'known_limitations':['PDF fraction characters and bars may be separated, especially inline image-mask bars.',
                                 'Algorithm line breaks and indentation can be lost during paragraph reconstruction.',
                                 'Preserving unassigned strokes prevents deletion; it does not repair formula grouping.'],
            'visual_review':{'status':'pending','required':True,
                             'checks':['inline fractions and fraction bars','superscripts and subscripts',
                                       'displayed equations','algorithm line breaks and indentation'],
                             'automatic_formula_integrity_proven':False}}
    logfile=scratch/'engine.log'
    try:
        try:
            report['source_risks'] = inspect_pdf_formula_risks(pdf_path)
        except Exception as error:
            # A review hint scanner must not silently certify documents it cannot inspect.
            report['source_risks'] = {'status':'unavailable','coverage':'none',
                                      'error_type':type(error).__name__}
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
        report['quality_status']='review_required'
        report['success_meaning']='PDF artifacts generated; formula and layout quality still requires visual review'
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as e:
        report['error']=str(e)
    finally:
        # The engine may include configuration in logs. Never retain a plaintext key.
        if logfile.exists() and adapter.api_key:
            raw=logfile.read_bytes().replace(adapter.api_key.encode(),b'[REDACTED]');logfile.write_bytes(raw)
        atomic_json(root/'fallback_report.json',report)
    return report['success']
