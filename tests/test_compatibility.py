"""Behavioral compatibility regressions; no network or live translation calls."""
import json
import shutil
from pathlib import Path
from unittest.mock import patch
from test_regression import Case, FakeAdapter, make_pdf, z, lc, pr, IntegrityError, unmask_latex_tokens


class MacroCompatibilityTests(Case):
    def document(self, definitions, body):
        return '\\documentclass{article}\n'+definitions+'\n\\begin{document}\n'+body+'\n\\end{document}'

    def accepted(self, definitions, body, hidden=()):
        text = self.document(definitions, body)
        root, adapter, _, before = self.translate(text, wrap=False)
        result = (root/'main.tex').read_text(encoding='utf-8')
        self.assertTrue(adapter.calls)
        self.assertIn(definitions, result)
        for token in hidden:
            self.assertFalse(any(token in request for request in adapter.calls))
        return root, adapter, result

    def rejected(self, definitions, body):
        root = self.project(self.document(definitions, body), wrap=False)
        before = (root/'main.tex').read_bytes()
        adapter = FakeAdapter()
        with self.assertRaises(IntegrityError): z.process_latex_project(root, adapter)
        self.assertEqual(adapter.calls, [])
        self.assertEqual((root/'main.tex').read_bytes(), before)

    def test_common_formatted_abbreviations(self):
        definitions = r'\newcommand{\eg}{\emph{e.g.}\xspace}\newcommand{\ie}{\textit{i.e.}\xspace}\newcommand{\etal}{\textit{et al.}\xspace}'
        _, _, result = self.accepted(definitions, r'The methods, \eg baselines, are compared by Smith \etal with \ie a fixed protocol.', ('baselines_opaque', 'et al.', 'e.g.', 'i.e.'))
        for token in [r'\eg',r'\ie',r'\etal']: self.assertIn(token, result)

    def test_zero_argument_declaration_forms(self):
        for definition in [r'\newcommand\sys{\textsc{ModelAlpha}}',r'\newcommand*{\sys}[0]{\textsc{ModelAlpha}}',r'\DeclareRobustCommand{\sys}{\textsc{ModelAlpha}}',r'\providecommand{\sys}{\textsc{ModelAlpha}}',r'\def\sys{\textsc{ModelAlpha}}',r'\gdef\sys{\textsc{ModelAlpha}}']:
            with self.subTest(definition=definition):
                self.accepted(definition, r'The system \sys improves recognition.', ('ModelAlpha',))

    def test_nested_alias_and_forward_definition(self):
        self.accepted(r'\newcommand{\sys}{\modelname\xspace}\newcommand{\modelname}{\textsf{ModelAlpha}}\let\alias=\sys', r'The \alias system uses \sys for classification.', ('ModelAlpha',))

    def test_noarg_macro_does_not_consume_following_prose_group(self):
        _, adapter, result = self.accepted(r'\newcommand{\sys}{ModelAlpha}', r'The \sys{} method handles {Important independent prose}.', ('ModelAlpha',))
        self.assertTrue(any('Important independent prose' in request for request in adapter.calls))
        self.assertIn(r'\sys{}', result)

    def test_restricted_ensuremath_and_symbols(self):
        self.accepted(r'\newcommand{\loss}{\ensuremath{\mathcal{L}_{\alpha}+\frac{1}{2}}}\newcommand{\yes}{\ensuremath{\checkmark}}', r'The objective \loss decreases and the mark \yes denotes success.', (r'\mathcal',r'\frac',r'\checkmark'))

    def test_comments_and_escaped_symbols_in_definitions(self):
        definition = '\\newcommand% target follows\n{\\sys}% body follows\n{\\textbf{Model\\_Alpha}\\xspace}'
        self.accepted(definition, r'The \sys improves recognition.', ('Model',))

    def test_definitions_from_static_input(self):
        text = self.document(r'\input{macros}',r'The \sys method uses samples.')
        root, adapter, _, before = self.translate(text, {'macros.tex':r'\def\sys{\textsc{ModelAlpha}\xspace}'}, wrap=False)
        self.assertEqual(before[root/'macros.tex'], (root/'macros.tex').read_bytes())
        self.assertFalse(any('ModelAlpha' in request for request in adapter.calls))

    def test_direct_xspace_and_checkmark(self):
        self.accepted('', r'The symbol \checkmark\xspace denotes successful recognition.', (r'\checkmark',))

    def test_model_removed_macro_delimiter_is_restored_for_chinese(self):
        text=self.document(r'\newcommand{\eg}{\emph{e.g.}\xspace}',r'Methods include \eg recognition.')
        root=self.project(text,wrap=False)
        z.process_latex_project(root,FakeAdapter(lambda text:'方法包括§LATEX_REF_0§图像识别。'))
        result=(root/'main.tex').read_text(encoding='utf-8')
        self.assertIn(r'\eg 图像识别',result)
        self.assertNotIn(r'\eg图像识别',result)

    def test_control_word_boundary_before_latin_text(self):
        self.assertEqual(unmask_latex_tokens('§LATEX_REF_0§Model',{'§LATEX_REF_0§':r'\TeX'},escape=True),r'\TeX Model')

    def test_boundary_insertion_does_not_change_frozen_formula_or_group(self):
        for raw in [r'$\alpha$',r'\ref{sec:method}',r'\sys{}']:
            with self.subTest(raw=raw):
                self.assertEqual(unmask_latex_tokens('§LATEX_REF_0§中文',{'§LATEX_REF_0§':raw},escape=True),raw+'中文')

    def test_unsafe_common_name_cannot_be_whitelisted(self):
        self.rejected(r'\newcommand{\eg}{\begin{tabular}{lr}}', r'Before rows. \eg SecretMethod & 90.3 \\ \end{tabular}')

    def test_unsafe_nested_definition_cannot_leak(self):
        self.rejected(r'\newcommand{\eg}{\hidden}\def\hidden{\input{private}}', r'Before results. \eg SecretMethod & 90.3')

    def test_unsafe_redefinition_of_standard_leaf(self):
        self.rejected(r'\renewcommand{\xspace}{\begin{table}}', r'Before results. \xspace SecretMethod & 90.3')

    def test_late_redefinition_invalidates_earlier_safe_alias(self):
        self.rejected(r'\newcommand{\eg}{\other}\newcommand{\other}{e.g.}', r'The method \eg is described. \renewcommand{\other}{\begin{table}} More prose.')

    def test_scoped_safe_definition_does_not_erase_unsafe_alternative(self):
        self.rejected(r'\def\sys{\begin{table}}{\def\sys{ModelAlpha}}', r'The method \sys is described.')

    def test_parameter_macros_remain_rejected(self):
        for definition in [r'\newcommand{\eg}[1]{\emph{#1}}',r'\def\eg#1{\emph{#1}}',r'\newcommand{\eg}[1][default]{\emph{#1}}']:
            with self.subTest(definition=definition): self.rejected(definition,r'The method \eg{Important prose} is described.')

    def test_recursive_aliases_are_bounded(self):
        self.rejected(r'\newcommand{\eg}{\other}\newcommand{\other}{\eg}',r'The method \eg is described.')

    def test_unknown_internal_macro_is_not_treated_as_a_control_symbol(self):
        self.rejected('',r'The method \hidden@rows is described.')

    def test_redefined_environment_primitive_is_not_implicitly_trusted(self):
        self.rejected(r'\def\begin#1{\input{private}}', 'The document contains prose.')

    def test_math_wrapper_cannot_hide_structural_commands(self):
        self.rejected(r'\newcommand{\loss}{\ensuremath{\input{private}}}',r'The loss \loss is reported.')

    def test_unsafe_primitive_definition_does_not_change_environment_stack(self):
        self.rejected(r'\def\opentable{\begin{table}}',r'The definition \opentable is unsafe.')

    def test_unused_unsafe_definition_is_not_a_false_rejection(self):
        self.accepted(r'\def\unused{\begin{table}}', 'This independent paragraph is translated.')


class ArchiveCompatibilityTests(Case):
    def fallback(self, pdf, output, **kwargs):
        make_pdf(Path(output)/'chinese_mono.pdf', chinese=True)
        lc.make_side_by_side_dual_pdf(pdf, Path(output)/'chinese_mono.pdf', Path(output)/'bilingual_dual.pdf')
        return True

    def run_local(self, source, out, **kwargs):
        with patch.object(z,'find_arxiv_id_from_pdf',return_value=None),patch.object(pr,'run_pdf_translation',side_effect=self.fallback):
            return z.auto_translate_paper(str(source),out,config={},**kwargs)

    def test_original_as_input_inside_output_is_preserved_and_rerunnable(self):
        out=self.root/'archive';out.mkdir();original=out/'original.pdf';make_pdf(original)
        before=original.read_bytes();mtime=original.stat().st_mtime_ns
        (out/'notes.txt').write_text('User notes')
        for _ in range(2):
            self.assertTrue(self.run_local(original,out))
            self.assertEqual(original.read_bytes(),before)
            self.assertEqual(original.stat().st_mtime_ns,mtime)
            manifest=json.loads((out/'translation_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['original_adoption']['action'],'preserved_matching_original')
        self.assertEqual((out/'notes.txt').read_text(),'User notes')

    def test_matching_pdf_copy_is_adopted(self):
        source=self.root/'download.pdf';make_pdf(source)
        out=self.root/'archive';out.mkdir();shutil.copy2(source,out/'original.pdf')
        self.assertTrue(self.run_local(source,out))

    def test_mismatched_preexisting_original_rejected_before_network(self):
        source=self.root/'download.pdf';make_pdf(source)
        out=self.root/'archive';out.mkdir();make_pdf(out/'original.pdf',pages=2)
        before=(out/'original.pdf').read_bytes()
        with patch.object(z,'find_arxiv_id_from_pdf') as network:
            with self.assertRaises(ValueError): z.auto_translate_paper(str(source),out,config={})
            network.assert_not_called()
        self.assertEqual((out/'original.pdf').read_bytes(),before)
        self.assertFalse((out/'translation_manifest.json').exists())

    def test_unverified_query_original_rejected(self):
        out=self.root/'archive';out.mkdir();make_pdf(out/'original.pdf')
        with patch.object(z,'search_arxiv_by_title') as search:
            with self.assertRaises(ValueError): z.auto_translate_paper('A paper title',out,config={})
            search.assert_not_called()

    def test_explicit_original_for_query_is_actually_used(self):
        out=self.root/'archive';out.mkdir();original=out/'original.pdf';make_pdf(original)
        before=original.read_bytes()
        with patch.object(z,'fetch_arxiv_source',return_value=False),patch.object(z,'download_arxiv_pdf') as download,patch.object(pr,'run_pdf_translation',side_effect=self.fallback):
            self.assertTrue(z.auto_translate_paper('2601.12345',out,config={},original=original))
            download.assert_not_called()
        self.assertEqual(original.read_bytes(),before)

    def test_source_project_with_matching_preexisting_original(self):
        source=self.project('The paper contains an English paragraph.');make_pdf(source/'original.pdf')
        out=self.root/'archive';out.mkdir();shutil.copy2(source/'original.pdf',out/'original.pdf')
        with patch.object(z,'process_latex_project',side_effect=RuntimeError('controlled failure')),patch.object(pr,'run_pdf_translation',side_effect=self.fallback):
            self.assertTrue(z.auto_translate_paper(str(source),out,config={}))

    def test_untracked_translations_still_rejected(self):
        source=self.root/'input.pdf';make_pdf(source)
        for name in ['chinese_mono.pdf','bilingual_dual.pdf','chinese_source.zip','chinese_source_uncompiled.zip']:
            with self.subTest(name=name):
                out=self.root/name.replace('.','_');out.mkdir();(out/name).write_bytes(b'existing artifact')
                with self.assertRaises(ValueError):self.run_local(source,out)
                self.assertEqual((out/name).read_bytes(),b'existing artifact')

    def test_conflicting_explicit_original_rejected(self):
        source=self.root/'input.pdf';make_pdf(source);other=self.root/'other.pdf';make_pdf(other,pages=2)
        with self.assertRaises(ValueError):self.run_local(source,self.root/'out',original=other)

    def test_original_modified_during_run_is_not_overwritten(self):
        out=self.root/'archive';out.mkdir();original=out/'original.pdf';make_pdf(original)
        def modified(pdf, directory, **kwargs):
            make_pdf(original,pages=2)
            return self.fallback(pdf,directory,**kwargs)
        with patch.object(z,'find_arxiv_id_from_pdf',return_value=None),patch.object(pr,'run_pdf_translation',side_effect=modified):
            self.assertFalse(z.auto_translate_paper(str(original),out,config={}))
        self.assertEqual(z.pdf_info(original)['pages'],2)
        self.assertFalse((out/'chinese_mono.pdf').exists())
        self.assertEqual(json.loads((out/'translation_manifest.json').read_text())['status'],'failed')

    def test_invalid_original_pdf_is_not_adopted(self):
        out=self.root/'archive';out.mkdir();original=out/'original.pdf';original.write_bytes(b'not a PDF')
        with self.assertRaises(Exception): self.run_local(original,out)
        self.assertEqual(original.read_bytes(),b'not a PDF')

    def test_tracked_source_original_is_reused_without_recompiling_english(self):
        source=self.project('The paper contains an English paragraph.')
        out=self.root/'archive';out.mkdir();original=out/'original.pdf';make_pdf(original)
        digest=z.sha256(original)
        (out/'translation_manifest.json').write_text(json.dumps({'input_identity':z._identity(str(source),exclude=[out]),'original_provenance':'recompiled_untouched_source','artifacts':{'original.pdf':{'sha256':digest}}}))
        with patch.object(z,'compile_latex_project') as compiler,patch.object(z,'process_latex_project',side_effect=RuntimeError('controlled failure')),patch.object(pr,'run_pdf_translation',side_effect=self.fallback):
            self.assertTrue(z.auto_translate_paper(str(source),out,config={}))
            compiler.assert_not_called()
        self.assertEqual(z.sha256(original),digest)
        self.assertEqual(json.loads((out/'translation_manifest.json').read_text())['original_provenance'],'recompiled_untouched_source')

    def test_tracked_original_tampering_is_detected_before_translation(self):
        source=self.project('The paper contains an English paragraph.')
        out=self.root/'archive';out.mkdir();original=out/'original.pdf';make_pdf(original)
        (out/'translation_manifest.json').write_text(json.dumps({'input_identity':z._identity(str(source),exclude=[out]),'artifacts':{'original.pdf':{'sha256':'different hash'}}}))
        with patch.object(z,'process_latex_project') as translator:
            with self.assertRaises(ValueError):z.auto_translate_paper(str(source),out,config={})
            translator.assert_not_called()
