"""Regressions for source identity and signed-number integrity; no network."""
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from test_regression import Case, FakeAdapter, make_pdf, z, lc, pr
from scripts.latex_syntax import ProjectPlan


class NumberIntegrityTests(Case):
    def test_signed_and_scientific_numbers_are_single_opaque_atoms(self):
        numbers = ['-0.5', '+0.25', '1e-3', '-2.5E+10', '−0.75', '.125', '-.5', '1,234.56']
        root = self.project('The measurements are '+', '.join(numbers)+'.')
        plan = ProjectPlan(root, root/'main.tex')
        frozen = [value for segment in plan.segments for value in segment.mapping.values()]
        for number in numbers:
            self.assertIn(number, frozen)
            self.assertFalse(any(number in segment.masked for segment in plan.segments))
        # This adapter omits every editable sign, but cannot alter a frozen one.
        z.process_latex_project(root, FakeAdapter())
        translated = (root/'main.tex').read_text(encoding='utf-8')
        for number in numbers:
            self.assertIn(number, translated)

    def test_prose_punctuation_and_words_are_still_translated(self):
        root = self.project('A well-known method gives -0.5. Next sentence has +1e-3.')
        plan = ProjectPlan(root, root/'main.tex')
        self.assertTrue(any('well-known method' in segment.masked for segment in plan.segments))
        self.assertTrue(any('Next sentence' in segment.masked for segment in plan.segments))


class SourceIdentityTests(Case):
    def text_pdf(self, path, text):
        import pymupdf
        with pymupdf.open() as doc:
            page=doc.new_page()
            page.insert_textbox(pymupdf.Rect(30,30,550,750),text)
            doc.save(path)

    def fallback(self, pdf, out, **kwargs):
        make_pdf(Path(out)/'chinese_mono.pdf', chinese=True)
        lc.make_side_by_side_dual_pdf(pdf, Path(out)/'chinese_mono.pdf', Path(out)/'bilingual_dual.pdf')
        return True

    def test_reference_to_another_paper_cannot_select_its_source(self):
        local=self.root/'input.pdf'; official=self.root/'other.pdf'
        self.text_pdf(local, 'Our original paper. For details see https://arxiv.org/abs/1706.03762.\n'+'Our findings. '*40)
        self.text_pdf(official, 'A completely different paper. '*40)
        before=local.read_bytes()
        def download(candidate, target):
            shutil.copy2(official,target)
            return True
        with patch.object(z,'download_arxiv_pdf',side_effect=download), patch.object(z,'fetch_arxiv_source') as source, patch.object(pr,'run_pdf_translation',side_effect=self.fallback):
            self.assertTrue(z.auto_translate_paper(str(local),self.root/'out',config={}))
            source.assert_not_called()
        manifest=json.loads((self.root/'out/translation_manifest.json').read_text(encoding='utf-8'))
        self.assertFalse(manifest['source_identity']['verified'])
        self.assertEqual(manifest['status'],'complete_fallback')
        self.assertEqual(local.read_bytes(),before)

    def test_identical_official_pdf_is_accepted(self):
        local=self.root/'input.pdf'; make_pdf(local)
        def download(candidate,target):
            shutil.copy2(local,target)
            return True
        with patch.object(z,'download_arxiv_pdf',side_effect=download):
            self.assertTrue(z.verify_arxiv_pdf_identity(local,'1706.03762',self.root/'reference.pdf'))

    def test_insufficient_text_and_download_failure_are_not_identity_proof(self):
        local=self.root/'input.pdf'; reference=self.root/'ref.pdf'
        self.text_pdf(local,'short');self.text_pdf(reference,'short')
        # Different metadata gives distinct bytes while keeping the same tiny text.
        import pymupdf
        with pymupdf.open(reference) as doc:
            doc.set_metadata({'title':'Different metadata'});doc.saveIncr()
        with patch.object(z,'download_arxiv_pdf',return_value=True):
            self.assertFalse(z.verify_arxiv_pdf_identity(local,'1706.03762',reference))
        with patch.object(z,'download_arxiv_pdf',return_value=False):
            self.assertFalse(z.verify_arxiv_pdf_identity(local,'1706.03762',reference))

    def test_filename_candidate_cannot_bypass_identity_check(self):
        local=self.root/'1706.03762.pdf';make_pdf(local)
        with patch.object(z,'verify_arxiv_pdf_identity',return_value=False) as verify, patch.object(z,'fetch_arxiv_source') as source, patch.object(pr,'run_pdf_translation',side_effect=self.fallback):
            self.assertTrue(z.auto_translate_paper(str(local),self.root/'out',config={}))
            verify.assert_called_once();source.assert_not_called()
