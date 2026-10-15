"""Run through Hermes: real native fractions, SCORE regression, and PDF review gate."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import zotero_translate as z
from scripts.latex_compiler import compile_latex_project
from scripts.project_utils import atomic_json, copy_project, sha256
from scripts.latex_syntax import ProjectPlan


FIXTURE=r'''\documentclass{article}
\usepackage{amsmath,amssymb,algorithm,algorithmic}
\begin{document}
\section{Inline fractions and score matching}
\looseness=-1An immediate observation is that the score is $s_j(x)=-\frac{x_j-f_j(x)}{\sigma_j^2}$.
The derivative is $\frac{\partial s_j(x)}{\partial x_j}=-\frac{1}{\sigma_j^2}$, and its variance is $\operatorname{Var}\left(\frac{\partial s_j(x)}{\partial x_j}\right)=0$.
The nested fraction is \(\frac{1+\frac{a}{b}}{c+\frac{d}{e}}\), while a second form is \ensuremath{\frac{\partial f_i}{\partial x_j}}.
\begin{equation}
\frac{\partial}{\partial x_i}\left(\frac{\partial f_i}{\partial x_j}\frac{x_i-f_i(x)}{\sigma_i^2}\right)=0.
\end{equation}
\begin{algorithm}
\caption{Score matching causal order search}
\begin{algorithmic}
\STATE Input: Data matrix $X\in\mathbb{R}^{n\times d}$
\STATE Initialize $\pi=[]$ and nodes $=\{1,\ldots,d\}$
\FOR{$k=1,\ldots,d$}
\STATE Estimate $V_j=\operatorname{Var}\left[\frac{\partial s_j(X)}{\partial x_j}\right]$
\STATE Select the node with the smallest variance
\STATE Remove the selected column of $X$
\ENDFOR
\STATE Return the final graph
\end{algorithmic}
\end{algorithm}
The algorithm retains the order of its instructions and its mathematical expressions.
\end{document}
'''


def snapshot(root):
    return {str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file()}


def run(base, case, source_project=None, original_pdf=None):
    base=Path(base).resolve();base.mkdir(parents=True,exist_ok=True)
    if case=='score':
        if not source_project or not original_pdf:
            raise ValueError('score requires --source-project and --original with matching SCORE inputs')
        source=copy_project(Path(source_project).resolve(),base/'inputs/score')
        original=Path(original_pdf).resolve()
        output=base/'outputs/score'
    else:
        source=base/'inputs/inline_fractions';source.mkdir(parents=True,exist_ok=True)
        (source/'main.tex').write_text(FIXTURE,encoding='utf-8')
        original=base/'inputs/inline_fractions_original.pdf'
        if not original.exists():
            ok,built,log=compile_latex_project(source,chinese=False)
            if not ok:raise RuntimeError('English fixture compilation failed: '+log)
            import shutil
            shutil.copy2(built,original)
        output=base/'outputs'/case
    # The PDF-only fixture may have rebuilt its English baseline on a previous
    # test run. A resumed case is bound to its own previously verified original.
    if (output/'original.pdf').exists():original=output/'original.pdf'
    original_digest=sha256(original)
    if case=='pdf_only':
        # No title/arXiv metadata: this deliberately exercises the pure PDF route.
        ok=z.auto_translate_paper(str(original),output,max_workers=2)
        manifest=json.loads((output/'translation_manifest.json').read_text(encoding='utf-8'))
        checks={'review_required':not ok and manifest['status']=='review_required',
                'pdf_route':manifest.get('mode')=='pdf_fallback','original_unchanged':sha256(original)==original_digest}
    else:
        before=snapshot(source)
        plan=ProjectPlan(source,source/'main.tex')
        # Preserve every opaque token from editable prose and algorithm bodies.
        formula_atoms=[raw for seg in plan.segments for raw in seg.mapping.values()
                       if raw.startswith(('$',r'\(',r'\[',r'\ensuremath'))]
        algorithms={str(p.relative_to(source)):re.findall(r'\\begin\{algorithmic\}.*?\\end\{algorithmic\}',text,re.S)
                    for p,text in plan.sources.items()}
        ok=z.auto_translate_paper(str(source),output,max_workers=4,original=str(original),no_fallback=True,compile_timeout=240)
        manifest=json.loads((output/'translation_manifest.json').read_text(encoding='utf-8'))
        translated=Path(manifest['run_dir'])/'translated'
        combined='\n'.join(p.read_bytes().decode('utf-8') for p in translated.rglob('*.tex') if '.build' not in p.parts)
        checks={'native_route':manifest.get('mode')=='latex_native',
                'pdfs_produced':all((output/n).is_file() for n in ['original.pdf','chinese_mono.pdf','bilingual_dual.pdf']),
                'formula_atoms_unchanged':all(raw in combined for raw in formula_atoms),
                'algorithm_bodies_unchanged':all(body in (translated/name).read_bytes().decode('utf-8') for name,bodies in algorithms.items() for body in bodies),
                'input_unchanged':before==snapshot(source),'original_unchanged':sha256(original)==original_digest,
                'archive_recompiled':manifest.get('archive_rebuild',{}).get('success') is True}
    result={'case':case,'status':manifest['status'],'mode':manifest.get('mode'),'checks':checks,
            'passed':all(checks.values()),'manifest':str(output/'translation_manifest.json'),
            'visual_review':'pending; programmatic checks do not prove PDF appearance'}
    atomic_json(base/(case+'_result.json'),result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True)
    parser.add_argument('--case',required=True,choices=['inline_native','score','pdf_only'])
    parser.add_argument('--source-project',help='Unmodified SCORE TeX source directory; required for score')
    parser.add_argument('--original',help='Matching English SCORE PDF; required for score')
    args=parser.parse_args()
    if args.case=='score' and not (args.source_project and args.original):
        parser.error('score requires --source-project and --original')
    sys.exit(0 if run(args.workspace,args.case,args.source_project,args.original) else 2)
