"""Live acceptance suite. Invoke through Hermes, not from a separate LLM client."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import zotero_translate as z
from scripts.latex_compiler import compile_latex_project
from scripts.project_utils import atomic_json,sha256


def create_fixtures(base):
    base=Path(base);base.mkdir(parents=True,exist_ok=True)
    p=base/'complex_native';p.mkdir(exist_ok=True)
    (p/'main.tex').write_text(r'''\documentclass[twocolumn]{article}
\usepackage{amsmath}
\usepackage{natbib}
\title{A controlled academic translation evaluation}
\author{A. Author}
\date{}
\begin{document}
\maketitle
\begin{abstract}
This study evaluates a method for image recognition. The reported results are experimental observations and should not be generalized beyond this setting.
\end{abstract}
\section{Method}\label{sec:method}
% A comment must not hide the following paragraph.
Our method learns a representation from unlabelled data. Its accuracy is 90.3 percent, and the reference result is 75.0 percent.
The representation is $x_i=90.3+\alpha$ and the normalization is \(y=x/2\).
\begin{align}
z_i &= \frac{x_i}{\sum_j x_j} \\
L &= -\sum_i z_i\log z_i
\end{align}
The preceding equation defines the normalization and the objective function.
\input{sections/results}
\section{Limitations}
The experiments use a limited sample size. The evidence does not establish that the proposed method is optimal for every dataset.
\bibliographystyle{plainnat}
\bibliography{references}
\end{document}
''',encoding='utf-8')
    (p/'sections').mkdir(exist_ok=True)
    (p/'sections/results.tex').write_text(r'''\section{Results}
Table~\ref{tab:results} compares the methods introduced in Section~\ref{sec:method}. These observations agree with earlier work~\citep[see][p.~2]{audit2026}.
\begin{table}[h]
\centering
\caption[Recognition results for the controlled evaluation]{Recognition accuracy for the controlled evaluation. The normalization uses $x_i$.}
\label{tab:results}
\begin{tabular}{lrr}
Method & Accuracy & Samples \\

\input{rows}

\end{tabular}
\end{table}
After the table, this paragraph must also be translated in full.
''',encoding='utf-8')
    (p/'sections/rows.tex').write_text('BaselineAlpha & 90.3 & 1000 \\\\\n\nProposedBeta & 75.0 & 2000 \\\\\n',encoding='utf-8')
    (p/'references.bib').write_text('@article{audit2026,author={Author, A.},title={A controlled recognition study},journal={Test Journal},year={2026},volume={1},pages={1--3}}\n',encoding='utf-8')
    b=base/'bbl_only';b.mkdir(exist_ok=True)
    (b/'main.tex').write_text(r'''\documentclass[twocolumn]{article}
\begin{document}
\section{Evidence}
The evidence in this study supports a limited conclusion~\cite{reference2026}. The result should be checked on independent samples.
\bibliographystyle{plain}
\bibliography{not_supplied}
\end{document}
''',encoding='utf-8')
    (b/'main.bbl').write_text(r'''\begin{thebibliography}{1}
\bibitem{reference2026} A. Author. Evidence from a controlled study. 2026.
\end{thebibliography}
''',encoding='utf-8')
    pdfbase=base/'pdf_source';pdfbase.mkdir(exist_ok=True)
    (pdfbase/'main.tex').write_text(r'''\documentclass{article}
\usepackage[margin=1in]{geometry}
\begin{document}
\section{Controlled recognition study}
This study evaluates a simple method for image recognition. The method learns a representation from a collection of training images. We compare the resulting classifier with a standard baseline on an independent set of test images.

The evaluation includes several limitations. The sample size is small, and the experiment covers only one dataset. The observations should therefore be interpreted cautiously. A higher score on this dataset does not prove that a method is suitable for every application.

The baseline reaches an accuracy of 75 percent. The proposed method reaches an accuracy of 90 percent. Further experiments are needed to determine whether this improvement is reproducible.
\end{document}
''',encoding='utf-8')
    import shutil
    if not (base/'pdf_only.pdf').exists():
        ok,pdf,log=compile_latex_project(pdfbase,chinese=False)
        if not ok:raise RuntimeError(log)
        shutil.copy2(pdf,base/'pdf_only.pdf')
    bad=base/'broken_native';bad.mkdir(exist_ok=True)
    shutil.copy2(base/'pdf_only.pdf',bad/'original.pdf')
    (bad/'main.tex').write_text(r'''\documentclass{article}
\ThisCommandCannotCompile
\begin{document}
This article contains ordinary English prose for translation.
\end{document}
''',encoding='utf-8')
    return {'complex_native':p,'bbl_only':b,'pdf_only':base/'pdf_only.pdf','broken_native':bad}


def snapshot(root):
    p=Path(root)
    if p.is_file():return {p.name:sha256(p)}
    return {str(f.relative_to(p)):sha256(f) for f in p.rglob('*') if f.is_file() and '.build' not in f.parts}


def run(base,cases):
    base=Path(base).resolve();fixtures=create_fixtures(base/'inputs')
    result={'runner':sys.executable,'root':str(ROOT),'cases':[]}
    for name in cases:
        source=fixtures[name];before=snapshot(source);output=base/'outputs'/name
        ok=z.auto_translate_paper(str(source),str(output),max_workers=2,no_fallback=name in {'complex_native','bbl_only'})
        manifest=json.loads((output/'translation_manifest.json').read_text(encoding='utf-8'))
        row={'name':name,'returned_success':ok,'status':manifest['status'],'mode':manifest.get('mode'),'input_unchanged':before==snapshot(source),'manifest':str(output/'translation_manifest.json'),'checks':{}}
        row['checks']['complete_expected_mode']=manifest['status']==('complete_native' if name in {'complex_native','bbl_only'} else 'complete_fallback')
        row['checks']['original_preserved']=row['input_unchanged']
        if name=='complex_native' and (output/'chinese_source.zip').exists():
            with zipfile.ZipFile(output/'chinese_source.zip') as archive:
                row['checks']['table_rows_byte_identical']=archive.read('sections/rows.tex')==(source/'sections/rows.tex').read_bytes()
                main=archive.read('main.tex').decode('utf-8');section=archive.read('sections/results.tex').decode('utf-8')
                original=(source/'main.tex').read_bytes().decode('utf-8')
                row['checks']['math_byte_identical']=all(expr in main for expr in [r'$x_i=90.3+\alpha$',r'\(y=x/2\)',re.search(r'\\begin\{align\}.*?\\end\{align\}',original,re.S).group()])
                row['checks']['reference_keys_unchanged']=r'\citep[see][p.~2]{audit2026}' in section
                row['checks']['percent_safe']=not bool(re.search(r'(?<!\\)%[^\n]*(?:准确|参见)',main))
        if name=='bbl_only' and (output/'chinese_source.zip').exists():
            with zipfile.ZipFile(output/'chinese_source.zip') as archive:
                row['checks']['bbl_byte_identical']=archive.read('main.bbl')==(source/'main.bbl').read_bytes()
        if name=='broken_native':row['checks']['uncompiled_source_retained']=(output/'chinese_source_uncompiled.zip').exists()
        row['passed']=bool(ok and all(row['checks'].values()))
        result['cases'].append(row);atomic_json(base/'acceptance_results.json',result)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    return all(r['passed'] for r in result['cases'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True)
    parser.add_argument('--cases',nargs='+',default=['complex_native','bbl_only','pdf_only','broken_native'])
    args=parser.parse_args();sys.exit(0 if run(args.workspace,args.cases) else 2)
