"""Deterministic regression tests. No live translation calls or user papers."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import zotero_translate as z,latex_compiler as lc,pdf_runner as pr
from scripts.latex_syntax import ProjectPlan,IntegrityError,TOKEN_RE,mask_latex_tokens,unmask_latex_tokens,balanced
from scripts.project_utils import safe_extract_tar,pdf_info
from adapters.openai_compatible import OpenAICompatibleAdapter


class FakeAdapter:
    model='test';base_url='http://localhost';api_key='test'
    def __init__(self,mutate=None):self.calls=[];self.mutate=mutate
    def translate(self,text,prompt):
        self.calls.append(text)
        return self.mutate(text) if self.mutate else '这是完整的中文译文。'+''.join(TOKEN_RE.findall(text))


def make_pdf(path,pages=1,chinese=False,links=False):
    import pymupdf as fitz
    with fitz.open() as doc:
        for i in range(pages):
            p=doc.new_page()
            p.insert_text((40,60),'中文测试页面' if chinese else f'Original page {i+1}',fontname='china-s' if chinese else 'helv')
            if links:p.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(40,40,140,65),'uri':'https://example.org'})
        doc.save(str(path))


class Case(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def project(self,body,extra=None,wrap=True):
        root=self.root/'source';root.mkdir(exist_ok=True)
        text='\\documentclass{article}\n\\begin{document}\n'+body+'\n\\end{document}' if wrap else body
        (root/'main.tex').write_text(text,encoding='utf-8')
        for name,value in (extra or {}).items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8')
        return root
    def translate(self,body,extra=None,wrap=True,adapter=None):
        root=self.project(body,extra,wrap);before={p:p.read_bytes() for p in root.rglob('*.tex')}
        a=adapter or FakeAdapter();report=z.process_latex_project(root,a,max_workers=2)
        return root,a,report,before


class ParserTests(Case):
    def test_dynamic_table_macros_cannot_leak_data(self):
        body=r'\documentclass{article}\newcommand{\openrows}{\begin{table}\begin{tabular}{lr}}\newcommand{\closerows}{\end{tabular}\end{table}}\begin{document}\openrows MethodAlpha & 90.3 \\ \closerows\end{document}'
        root=self.project(body,wrap=False);adapter=FakeAdapter()
        with self.assertRaises(IntegrityError):z.process_latex_project(root,adapter)
        self.assertEqual(adapter.calls,[])
    def test_declared_literal_macro_is_safe_opaque(self):
        body=r'\documentclass{article}\newcommand{\methodname}{MethodAlpha}\begin{document}The method \methodname improves recognition.\end{document}'
        root,adapter,report,before=self.translate(body,wrap=False)
        self.assertTrue(adapter.calls);self.assertFalse(any('MethodAlpha' in t for t in adapter.calls))
        self.assertIn(r'\methodname',(root/'main.tex').read_text(encoding='utf-8'))
    def test_first_api_failure_cancels_queued_requests(self):
        import time
        class FailingAdapter(FakeAdapter):
            def translate(self,text,prompt):
                self.calls.append(text);time.sleep(0.02)
                raise RuntimeError('Provider unavailable')
        root=self.project('\n\n'.join('The experimental observation number '+str(i)+' is recorded.' for i in range(40)))
        before=(root/'main.tex').read_bytes();adapter=FailingAdapter()
        with self.assertRaises(RuntimeError):z.process_latex_project(root,adapter,max_workers=1)
        self.assertLess(len(adapter.calls),10)
        self.assertEqual(before,(root/'main.tex').read_bytes())
    def test_all_table_environment_types_and_blank_lines(self):
        for env in sorted(z.ProjectPlan.__module__ and __import__('scripts.latex_syntax',fromlist=['TABLE_ENVS']).TABLE_ENVS):
            with self.subTest(env=env):
                body='Before table prose.\n\\begin{'+env+'}\n\nMethodAlpha & 90.3 \\\\\n\n\\caption[Long optional English title]{A complete result caption}\n\\end{'+env+'}\nAfter table prose.'
                root,a,report,before=self.translate(body)
                self.assertFalse(any('90.3' in c or 'MethodAlpha' in c for c in a.calls))
                self.assertIn('MethodAlpha & 90.3', (root/'main.tex').read_text(encoding='utf-8'))
                self.assertEqual(report['segments'],4)
    def test_input_table_rows(self):
        root,a,_,before=self.translate(r'\begin{table}\begin{tabular}{lr}\input{rows}\end{tabular}\caption{A result}\end{table}'+'\nEnglish prose.',{'rows.tex':'MethodAlpha & 90.3 \\\\\n\nOtherMethod & 75.0 \\\\'})
        self.assertEqual(before[root/'rows.tex'],(root/'rows.tex').read_bytes())
        self.assertFalse(any('MethodAlpha' in c or '90.3' in c for c in a.calls))
    def test_environment_crosses_input_boundary(self):
        root,a,_,before=self.translate(r'\begin{table}\input{rows}'+'\nAfter table prose.',{'rows.tex':r'\begin{tabular}{lr}MethodAlpha & 90.3 \\\end{tabular}\caption{A result}\end{table}'})
        self.assertFalse(any('90.3' in c for c in a.calls))
        self.assertIn('MethodAlpha & 90.3',(root/'rows.tex').read_text(encoding='utf-8'))
    def test_inline_and_display_math(self):
        expressions=[r'$x_i=90.3$',r'$$\alpha+75.0$$',r'\(x^2\)',r'\[\frac{1}{2}\]']
        root,a,_,_=self.translate('The expressions are '+' and '.join(expressions)+'.')
        out=(root/'main.tex').read_text(encoding='utf-8')
        for expr in expressions:self.assertIn(expr,out)
        self.assertFalse(any('90.3' in c or '\\frac' in c for c in a.calls))
    def test_comment_does_not_skip_body(self):
        _,a,report,_=self.translate('% Skip only this comment\nTranslate this English paragraph.')
        self.assertEqual(report['segments'],1);self.assertIn('Translate this',a.calls[0])
    def test_no_blank_lines(self):
        _,a,report,_=self.translate('Translate this English paragraph.')
        self.assertEqual(report['segments'],1)
    def test_adjacent_formula_does_not_skip_prose(self):
        _,a,report,_=self.translate('Translate the preceding prose.\n'+r'\begin{equation}x=1\end{equation}'+'\nTranslate the following prose.')
        self.assertEqual(report['segments'],2)
    def test_code_is_frozen(self):
        for env in ['algorithm','algorithmic','lstlisting','minted','verbatim']:
            with self.subTest(env=env):
                body='\\begin{'+env+'}\nProgramMarker = 90.3\n\nProgramOther = 75.0\n\\end{'+env+'}\nTranslate this paragraph.'
                _,a,_,_=self.translate(body)
                self.assertFalse(any('ProgramMarker' in c for c in a.calls))
    def test_caption_math_and_label_protected(self):
        body=r'\begin{table}\caption[Optional long caption]{Accuracy $x=90.3$ and \ref{sec:abc}}\label{tab:test}\end{table}'
        root,a,_,_=self.translate(body)
        out=(root/'main.tex').read_text(encoding='utf-8')
        for token in [r'$x=90.3$',r'\ref{sec:abc}',r'\label{tab:test}']:self.assertIn(token,out)
        self.assertFalse(any('90.3' in c or 'sec:abc' in c for c in a.calls))
    def test_reserved_placeholder_rejected(self):
        with self.assertRaises(IntegrityError):self.translate('The source contains §LATEX_REF_0§ here.')
    def test_missing_placeholder_rejected_without_writing(self):
        root=self.project(r'The reference is \cite{key}.');before=(root/'main.tex').read_bytes()
        with self.assertRaises(IntegrityError):z.process_latex_project(root,FakeAdapter(lambda s:'中文译文'))
        self.assertEqual(before,(root/'main.tex').read_bytes())
    def test_duplicate_and_reordered_placeholders_rejected(self):
        _,mapping=mask_latex_tokens(r'\cite{key}\ref{sec}')
        for text in ['§LATEX_REF_0§§LATEX_REF_0§','§LATEX_REF_1§§LATEX_REF_0§','§LATEX_REF_0§§LATEX_REF_99§']:
            with self.subTest(text=text),self.assertRaises(IntegrityError):unmask_latex_tokens(text,mapping)
    def test_reference_forms_roundtrip(self):
        source=r'\citep[see][p. 2]{key} \citet*{key} \ref {sec:test} \url{https://example.org/a} \Cref{fig:1}'
        masked,mapping=mask_latex_tokens(source)
        self.assertNotIn('key',masked);self.assertNotIn('sec:test',masked)
        self.assertEqual(unmask_latex_tokens(masked,mapping),source)
    def test_generated_special_characters_escaped(self):
        root,_,_,_=self.translate('The accuracy is excellent.',adapter=FakeAdapter(lambda s:'准确率为 90.3% & #1_value，包含 {符号}。'))
        out=(root/'main.tex').read_text(encoding='utf-8')
        for token in [r'90.3\%',r'\&',r'\#',r'\_',r'\{']:self.assertIn(token,out)
    def test_source_numbers_are_opaque(self):
        _,a,_,_=self.translate('The score is 90.3 and the population is 12345.')
        self.assertFalse(any('90.3' in c or '12345' in c for c in a.calls))
    def test_escaped_brace_caption(self):
        root,_,_,_=self.translate(r'\begin{table}\caption{The literal \{ symbol is preserved}\end{table}')
        self.assertIn(r'\{',(root/'main.tex').read_text(encoding='utf-8'))
    def test_unknown_text_macro_fails_closed(self):
        with self.assertRaises(IntegrityError):self.translate(r'\mystery{Important English content}')
    def test_recursive_input_rejected(self):
        with self.assertRaises(IntegrityError):self.translate(r'\input{rows}',{'rows.tex':r'\input{main}'})
    def test_escaping_input_rejected(self):
        (self.root/'outside.tex').write_text('English prose.')
        with self.assertRaises(IntegrityError):self.translate(r'\input{../outside}')
    def test_unclosed_environment_rejected(self):
        with self.assertRaises(IntegrityError):self.translate(r'\begin{table} frozen data')
    def test_unknown_environment_rejected(self):
        with self.assertRaises(IntegrityError):self.translate(r'\begin{custommath}HiddenVariable\end{custommath}')
    def test_declared_theorem_text_is_translated(self):
        text=r'\documentclass{article}\newtheorem{customthm}{Theorem}\begin{document}\begin{customthm}Every object has this property.\end{customthm}\end{document}'
        _,a,report,_=self.translate(text,wrap=False)
        self.assertEqual(report['segments'],1)
    def test_math_comment_dollar_is_not_a_delimiter(self):
        math='$x % ignored dollar $\n+y$'
        root,a,_,_=self.translate('The formula is '+math+'.')
        self.assertIn(math,(root/'main.tex').read_text(encoding='utf-8'))
    def test_unused_tex_file_not_translated(self):
        root,a,_,before=self.translate('English body.',{'unused.tex':'UnusedMarker should not be sent.'})
        self.assertEqual(before[root/'unused.tex'],(root/'unused.tex').read_bytes())
    def test_cache_and_transaction(self):
        root=self.project('Some English prose.');text=(root/'main.tex').read_bytes();cache=self.root/'cache.json'
        a=FakeAdapter();z.process_latex_project(root,a,cache_path=cache)
        (root/'main.tex').write_bytes(text);b=FakeAdapter();report=z.process_latex_project(root,b,cache_path=cache)
        self.assertEqual(len(b.calls),0);self.assertEqual(report['cache_hits'],1)


class CompilerTests(Case):
    def test_legacy_font_shim_does_not_replace_template(self):
        root=self.project('Hello world.');p=root/'main.tex'
        lc.inject_legacy_font_support(p,['ptm']);lc.inject_legacy_font_support(p,['ptm'])
        out=p.read_text(encoding='utf-8')
        self.assertEqual(out.count(lc.FONT_BEGIN),1)
        self.assertLess(out.index('\\setmainfont'),out.index('\\begin{document}'))
        self.assertNotIn('\\setsansfont',out)
        self.assertIn('Hello world.',out)
    def test_injection_ignores_commented_documentclass(self):
        root=self.project('% \\documentclass{obsolete}\n\\documentclass{article}\n\\begin{document}Hello world.\\end{document}',wrap=False)
        p=root/'main.tex';lc.inject_chinese_support(p)
        out=p.read_text(encoding='utf-8')
        self.assertTrue(out.startswith('% \\documentclass{obsolete}\n\\documentclass{article}'))
        self.assertGreater(out.index(lc.BEGIN),out.index('\\documentclass{article}'))
    def test_bibtex_failure_rejects_even_new_pdf(self):
        root=self.project('Hello world.',extra={'references.bib':'@article{key,title={Example}}'})
        def execute(cmd,cwd,timeout,env,logfile):
            cwd=Path(cwd)
            if cmd[0]=='bibtex':return 1,'Bibliography failure'
            (cwd/'main.aux').write_text(r'\bibdata{references}')
            make_pdf(cwd/'main.pdf')
            return 0,'Successful TeX pass'
        with patch.object(lc.shutil,'which',return_value='xelatex'), patch.object(lc,'_run',side_effect=execute) as runner:
            ok,pdf,report=lc.compile_latex_project(root)
        self.assertFalse(ok);self.assertIsNone(pdf);self.assertIn('Bibliography failure',report)
        self.assertIn('bibtex',[call.args[0][0] for call in runner.call_args_list])
    def test_ctex_switch_replaces_managed_block(self):
        root=self.project('Hello world.');p=root/'main.tex'
        lc.inject_chinese_support(p);lc.inject_chinese_support(p,True)
        out=p.read_text(encoding='utf-8')
        self.assertIn(r'\usepackage{xeCJK}',out);self.assertNotIn('{ctex}',out)
        self.assertEqual(out.count(lc.BEGIN),1)
    def test_failed_compile_cannot_reuse_old_pdf(self):
        root=self.project('Hello world.');make_pdf(root/'main.pdf');before=(root/'main.pdf').read_bytes()
        with patch.object(lc.shutil,'which',return_value='xelatex'), patch.object(lc,'_run',return_value=(1,'fatal simulated')) as runner:
            ok,pdf,report=lc.compile_latex_project(root)
        self.assertFalse(ok);self.assertIsNone(pdf);self.assertEqual(before,(root/'main.pdf').read_bytes())
        self.assertTrue(runner.called);self.assertIn('fatal simulated',report)
    def test_bbl_preserved_during_retry_and_pack(self):
        root=self.project('Hello world.');bbl=root/'main.bbl';bbl.write_text('Only bibliography source')
        with patch.object(lc.shutil,'which',return_value='xelatex'), patch.object(lc,'_run',return_value=(1,'fatal')) as runner:
            lc.compile_latex_project(root)
        self.assertTrue(runner.called)
        self.assertTrue(bbl.exists())
        archive=root/'chinese_source.zip';lc.pack_source_zip(root,archive)
        with zipfile.ZipFile(archive) as zf:
            self.assertIn('main.bbl',zf.namelist());self.assertNotIn('chinese_source.zip',zf.namelist())
            self.assertFalse(any('.build/' in n for n in zf.namelist()))
    def test_dual_keeps_tail_and_links(self):
        import pymupdf
        original=self.root/'original.pdf';mono=self.root/'mono.pdf';dual=self.root/'dual.pdf'
        make_pdf(original,1,links=True);make_pdf(mono,2,chinese=True)
        lc.make_side_by_side_dual_pdf(original,mono,dual)
        with pymupdf.open(dual) as d:
            self.assertEqual(len(d),2);self.assertIn('No corresponding page',d[1].get_text())
            self.assertIn('中文',d[1].get_text());self.assertEqual(len(d[0].get_links()),1)
    def test_ambiguous_entry_fails(self):
        root=self.project('Hello.');(root/'main.tex').rename(root/'a.tex');(root/'b.tex').write_bytes((root/'a.tex').read_bytes())
        with self.assertRaises(ValueError):lc.find_main_tex(root)
    def test_gbk_bytes_do_not_crash_log_capture(self):
        cp=subprocess.CompletedProcess([],0,b'\x81\x82',b'\xff')
        with patch.object(lc.subprocess,'run',return_value=cp):
            rc,text=lc._run(['unused'],self.root,1,{},self.root/'log.txt')
        self.assertEqual(rc,0);self.assertTrue((self.root/'log.txt').exists())


class RoutingTests(Case):
    def test_provider_selection(self):
        self.assertIsInstance(z.get_adapter('deepseek',{}),z.DeepSeekAdapter)
        self.assertIsInstance(z.get_adapter('ollama',{}),z.OllamaAdapter)
    def test_title_input_searches(self):
        with patch.object(z,'search_arxiv_by_title',return_value=None) as search:
            ok=z.auto_translate_paper('Attention Is All You Need',self.root/'out',config={})
        self.assertFalse(ok);search.assert_called_once()
    def test_arxiv_filename_retains_local_pdf(self):
        path=self.root/'2301.12345.pdf';make_pdf(path)
        def fallback(pdf,out,**kwargs):
            make_pdf(Path(out)/'chinese_mono.pdf',chinese=True);lc.make_side_by_side_dual_pdf(pdf,Path(out)/'chinese_mono.pdf',Path(out)/'bilingual_dual.pdf');return True
        with patch.object(z,'find_arxiv_id_from_pdf',return_value=None),patch.object(z,'verify_arxiv_pdf_identity',return_value=False),patch.object(z,'fetch_arxiv_source',return_value=False),patch.object(pr,'run_pdf_translation',side_effect=fallback) as fb:
            ok=z.auto_translate_paper(str(path),self.root/'out',config={})
        self.assertTrue(ok);fb.assert_called_once()
    def test_translation_exception_enters_fallback_and_input_unchanged(self):
        root=self.project('Hello world.');make_pdf(root/'original.pdf');before=(root/'main.tex').read_bytes()
        def fallback(pdf,out,**kwargs):
            make_pdf(Path(out)/'chinese_mono.pdf',chinese=True);lc.make_side_by_side_dual_pdf(pdf,Path(out)/'chinese_mono.pdf',Path(out)/'bilingual_dual.pdf');return True
        with patch.object(z,'process_latex_project',side_effect=TimeoutError('simulated timeout')),patch.object(pr,'run_pdf_translation',side_effect=fallback) as fb:
            ok=z.auto_translate_paper(str(root),self.root/'out',config={})
        self.assertTrue(ok);fb.assert_called_once();self.assertEqual(before,(root/'main.tex').read_bytes())
        self.assertTrue((self.root/'out/chinese_source_uncompiled.zip').exists())
    def test_fallback_empty_outputs_is_failure(self):
        original=self.root/'original.pdf';make_pdf(original)
        with patch.object(pr.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
            self.assertFalse(pr.run_pdf_translation(original,self.root/'out',config={}))
    def test_output_rejects_different_paper(self):
        out=self.root/'out';out.mkdir();(out/'translation_manifest.json').write_text(json.dumps({'input_identity':'different'}))
        with self.assertRaises(ValueError):z.auto_translate_paper('2601.12345',out,config={})
    def test_failure_exit_nonzero(self):
        with patch.object(z,'auto_translate_paper',return_value=False),patch.object(sys,'argv',['translate','--input','test']):
            self.assertEqual(z.main(),2)
    def test_input_overwrite_rejected(self):
        root=self.project('English prose.')
        with self.assertRaises(ValueError):z.auto_translate_paper(str(root),root,config={})
    def test_archive_traversal_and_symlink_rejected(self):
        for name,kind in [('../escape.tex',tarfile.REGTYPE),('C:/escape.tex',tarfile.REGTYPE),('a',tarfile.SYMTYPE)]:
            with self.subTest(name=name):
                path=self.root/'input.tar'
                with tarfile.open(path,'w') as t:
                    item=tarfile.TarInfo(name);item.type=kind;item.size=0;item.linkname='../escape';t.addfile(item,io.BytesIO())
                with self.assertRaises(ValueError):safe_extract_tar(path,self.root/'extract')
    def test_adapter_rejects_truncation(self):
        a=OpenAICompatibleAdapter('http://localhost','test','test')
        payload={'choices':[{'message':{'content':'中文'},'finish_reason':'length'}]}
        with patch('urllib.request.build_opener') as op:
            op.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(payload).encode()
            with self.assertRaises(ValueError):a.translate('Some source','__SOURCE_TEXT__')

    def test_output_lock_blocks_concurrent_run(self):
        out=self.root/'locked';lock=out/'.translation'/'active.lock';lock.parent.mkdir(parents=True);lock.write_text('occupied')
        with self.assertRaises(ValueError):z.auto_translate_paper('some title',out,config={})
        self.assertTrue(lock.exists())

    def test_workers_validated_before_network(self):
        with self.assertRaises(ValueError):z.auto_translate_paper('some title',self.root/'out',max_workers=0)

    def test_optional_column_title_and_author_metadata(self):
        root,a,report,_=self.translate(r'\twocolumn[\icmltitle{A scientific title}\icmlauthor{AuthorName}{inst}]'+'\nThe paper body is here.')
        self.assertFalse(any('AuthorName' in c for c in a.calls));self.assertEqual(report['segments'],2)

    def test_pdf_arxiv_url_detection(self):
        import pymupdf
        path=self.root/'article.pdf'
        with pymupdf.open() as d:
            p=d.new_page();p.insert_text((30,50),'https://arxiv.org/abs/1706.03762v7');d.save(path)
        self.assertEqual(z.find_arxiv_id_from_pdf(path),'1706.03762v7')


if __name__=='__main__':unittest.main(verbosity=2)
