"""PDF layout regressions: geometry hints and generation are not quality approval."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import pdf_runner as pr
from scripts import zotero_translate as z


def create_pdf(path, fraction=False, algorithm=False, image_mask=False):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), 'An ordinary research paragraph.')
        if fraction:
            page.insert_text((104, 94), 'x', fontsize=8)
            if image_mask:
                content = page.read_contents()
                content += (f'\nq 20 0 0 0.5 100 {page.rect.height - 100.25} cm\n'
                            'BI /W 1 /H 1 /BPC 1 /IM true ID ').encode() + b'\x00\nEI Q\n'
                stream = document.get_new_xref()
                document.update_object(stream, '<<>>')
                document.update_stream(stream, content)
                page.set_contents(stream)
            else:
                page.draw_line((100, 100), (120, 100), width=0.5)
            page.insert_text((104, 112), 'y', fontsize=8)
        if algorithm:
            page.insert_text((40, 160), 'Algorithm 1 Example procedure')
            page.insert_text((50, 180), 'for each sample')
            page.insert_text((60, 196), 'update score')
            page.insert_text((50, 212), 'end for')
        document.save(path)


class PdfFormulaOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def test_fraction_and_algorithm_pages_are_review_hints(self):
        create_pdf(self.source, fraction=True, algorithm=True)
        result = pr.inspect_pdf_formula_risks(self.source)
        self.assertEqual(result['fraction_candidate_pages'], [1])
        self.assertEqual(result['algorithm_heading_pages'], [1])
        self.assertEqual(result['priority_review_pages'], [1])
        self.assertEqual(result['coverage'], 'heuristic_incomplete')

    def test_plain_page_is_not_a_formula_hint(self):
        create_pdf(self.source)
        result = pr.inspect_pdf_formula_risks(self.source)
        self.assertEqual(result['priority_review_pages'], [])
        self.assertEqual(result['coverage'], 'heuristic_incomplete')

    def test_inline_image_mask_fraction_is_not_missed_by_drawing_only_scan(self):
        create_pdf(self.source, fraction=True, image_mask=True)
        with fitz.open(self.source) as document:
            self.assertEqual(document[0].get_drawings(), [])
            self.assertEqual(document[0].get_images(), [])
            self.assertIn('fill-imgmask', [kind for kind, _ in document[0].get_bboxlog()])
        result = pr.inspect_pdf_formula_risks(self.source)
        self.assertEqual(result['inline_image_mask_fraction_pages'], [1])
        self.assertEqual(result['fraction_candidate_counts'], {'1': 1})

    def test_false_switch_is_not_enabled_by_string_truthiness(self):
        with self.assertRaises(ValueError):
            pr._layout_options({'split_short_lines': 'false'})
        for invalid in [float('nan'), float('inf'), 0, -1]:
            with self.assertRaises(ValueError):
                pr._layout_options({'split_short_lines': True, 'short_line_split_factor': invalid})

    def test_short_lines_are_opt_in_not_a_formula_repair_claim(self):
        args, options = pr._layout_options({'split_short_lines': True})
        self.assertIn('--split-short-lines', args)
        self.assertEqual(options['short_line_split_factor'], 0.8)
        defaults, options = pr._layout_options({})
        self.assertNotIn('--split-short-lines', defaults)
        self.assertIn('--no-remove-non-formula-lines', defaults)

    def run_fake_engine(self, scan_failure=False):
        create_pdf(self.source, fraction=True, algorithm=True)
        adapter = SimpleNamespace(base_url='http://127.0.0.1:1', model='fake',
                                  timeout=1, api_key='test-private-placeholder')
        observed = {}

        def engine(cmd, **kwargs):
            observed['command'] = cmd
            observed['environment'] = kwargs['env']
            output = Path(cmd[cmd.index('--output') + 1])
            create_pdf(output / 'result-mono.pdf', fraction=True)
            kwargs['stdout'].write(adapter.api_key.encode())
            return SimpleNamespace(returncode=0)

        patches = [patch.object(z, 'get_adapter', return_value=adapter),
                   patch.object(pr.subprocess, 'run', side_effect=engine)]
        if scan_failure:
            patches.append(patch.object(pr, 'inspect_pdf_formula_risks', side_effect=RuntimeError('unavailable')))
        from contextlib import ExitStack
        with ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            self.assertTrue(pr.run_pdf_translation(self.source, self.root / 'out', config={}))
        report = json.loads((self.root / 'out' / 'fallback_report.json').read_text())
        return observed, report, adapter

    def test_generated_pdf_never_implies_formula_approval(self):
        observed, report, adapter = self.run_fake_engine()
        self.assertIn('babeldoc==0.6.2', observed['command'])
        self.assertNotIn(adapter.api_key, ' '.join(observed['command']))
        self.assertEqual(report['quality_status'], 'review_required')
        self.assertEqual(report['visual_review']['status'], 'pending')
        self.assertFalse(report['visual_review']['automatic_formula_integrity_proven'])
        self.assertEqual(report['source_risks']['priority_review_pages'], [1])
        log = next((self.root / 'out').glob('pdf_fallback_*/engine.log')).read_text()
        self.assertNotIn(adapter.api_key, log)

    def test_failed_hint_scan_cannot_imply_no_formula_risk(self):
        _, report, _ = self.run_fake_engine(scan_failure=True)
        self.assertEqual(report['source_risks']['status'], 'unavailable')
        self.assertEqual(report['source_risks']['coverage'], 'none')
        self.assertEqual(report['quality_status'], 'review_required')


if __name__ == '__main__':
    unittest.main()
