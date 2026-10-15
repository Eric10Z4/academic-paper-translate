"""Source availability and entry selection are separate facts; no live I/O."""
import gzip
import io
import json
import tarfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from test_regression import Case, FakeAdapter, make_pdf, z, lc, pr


DOCUMENT = r'\documentclass{article}\begin{document}A complete paper describes the method.\end{document}'


class SourceAcquisitionTests(Case):
    def archive_bytes(self, documents=None):
        documents = documents or {'article.tex': DOCUMENT, 'conference_template.tex': DOCUMENT}
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, text in documents.items():
                payload = text.encode('utf-8')
                entry = tarfile.TarInfo(name)
                entry.size = len(payload)
                entry.mtime = 1577836800  # Valid ZIP timestamp, 2020-01-01.
                archive.addfile(entry, io.BytesIO(payload))
        return stream.getvalue()

    def downloaded(self, payload):
        def save(url, target, *args, **kwargs):
            Path(target).write_bytes(payload)
        return save

    def report(self, source):
        return json.loads((source.parent/'source_acquisition.json').read_text(encoding='utf-8'))

    def fallback(self, pdf, output, **kwargs):
        output = Path(output)
        make_pdf(output/'chinese_mono.pdf', chinese=True)
        lc.make_side_by_side_dual_pdf(pdf, output/'chinese_mono.pdf', output/'bilingual_dual.pdf')
        return True

    def translate_query(self, **kwargs):
        original = self.root/'original.pdf'
        make_pdf(original)
        output = self.root/'output'
        result = z.auto_translate_paper('2203.04413', output, original=original, config={}, **kwargs)
        manifest = json.loads((output/'translation_manifest.json').read_text(encoding='utf-8'))
        return result, output, manifest

    def test_network_failure_leaves_source_availability_unknown(self):
        source = self.root/'run/source'
        failure = urllib.error.URLError('TLS peer closed connection')
        with patch.object(z, '_download', side_effect=failure) as download:
            self.assertFalse(z.fetch_arxiv_source('2203.04413', source))
        download.assert_called_once()
        report = self.report(source)
        self.assertEqual(report['status'], 'retrieval_failed')
        self.assertIsNone(report['source_available'])
        self.assertEqual(report['error_type'], 'URLError')
        self.assertIn('TLS peer closed', report['detail'])
        self.assertFalse((source.parent/'source.download.gz').exists())

    def test_raw_and_gzipped_pdf_responses_are_not_tex_sources(self):
        for name, payload in [('raw', b'%PDF-1.7\nPDF-only submission'),
                              ('gzip', gzip.compress(b'%PDF-1.7\nPDF-only submission'))]:
            with self.subTest(response=name):
                source = self.root/name/'source'
                with patch.object(z, '_download', side_effect=self.downloaded(payload)):
                    self.assertFalse(z.fetch_arxiv_source('2203.04413', source))
                report = self.report(source)
                self.assertEqual(report['status'], 'endpoint_returned_pdf')
                self.assertIs(report['source_available'], False)
                self.assertFalse((source/'main.tex').exists())
                self.assertFalse((source.parent/'source.download.gz').exists())

    def test_html_response_does_not_prove_source_unavailable(self):
        source = self.root/'run/source'
        with patch.object(z, '_download', side_effect=self.downloaded(b'<html>Temporarily unavailable</html>')):
            self.assertFalse(z.fetch_arxiv_source('2203.04413', source))
        self.assertEqual(self.report(source)['status'], 'unrecognized_response')
        self.assertIsNone(self.report(source)['source_available'])

    def test_archive_without_supported_tex_does_not_prove_source_unavailable(self):
        source = self.root/'run/source'
        with patch.object(z, '_download', side_effect=self.downloaded(self.archive_bytes({'paper.ltx':DOCUMENT}))):
            self.assertFalse(z.fetch_arxiv_source('2203.04413', source))
        self.assertEqual(self.report(source)['status'], 'no_supported_tex_files')
        self.assertIsNone(self.report(source)['source_available'])

    def test_multiple_document_entries_do_not_make_source_download_fail(self):
        source = self.root/'run/source'
        with patch.object(z, '_download', side_effect=self.downloaded(self.archive_bytes())):
            self.assertTrue(z.fetch_arxiv_source('2203.04413', source))
        report = self.report(source)
        self.assertEqual(report['status'], 'source_downloaded')
        self.assertIs(report['source_available'], True)
        self.assertEqual(set(report['tex_files']), {'article.tex', 'conference_template.tex'})
        with self.assertRaisesRegex(ValueError, 'Ambiguous TeX entry'):
            lc.find_main_tex(source)
        self.assertEqual((source/'article.tex').read_text(encoding='utf-8'), DOCUMENT)

    def test_network_failure_is_reported_in_manifest_and_requires_review(self):
        with patch.object(z, '_download', side_effect=urllib.error.URLError('TLS EOF')), \
             patch.object(z, 'get_adapter') as adapter, \
             patch.object(pr, 'run_pdf_translation', side_effect=self.fallback) as fallback:
            result, output, manifest = self.translate_query()
        self.assertFalse(result)
        adapter.assert_not_called()
        fallback.assert_called_once()
        self.assertEqual(manifest['source_acquisition']['status'], 'retrieval_failed')
        self.assertIsNone(manifest['source_acquisition']['source_available'])
        self.assertTrue(any(error['stage']=='source_retrieval' and 'TLS EOF' in error['detail']
                            for error in manifest['errors']))
        self.assertEqual(manifest['mode'], 'pdf_fallback')
        self.assertEqual(manifest['status'], 'review_required')
        self.assertEqual(manifest['visual_review']['status'], 'pending')
        self.assertTrue((output/'chinese_mono.pdf').is_file())

    def test_ambiguous_entry_is_preserved_and_reported_before_fallback(self):
        with patch.object(z, '_download', side_effect=self.downloaded(self.archive_bytes())), \
             patch.object(z, 'get_adapter') as adapter, \
             patch.object(pr, 'run_pdf_translation', side_effect=self.fallback) as fallback:
            result, output, manifest = self.translate_query()
        self.assertFalse(result)
        adapter.assert_not_called()
        fallback.assert_called_once()
        self.assertIs(manifest['source_acquisition']['source_available'], True)
        self.assertEqual(manifest['source_acquisition']['status'], 'source_downloaded')
        self.assertTrue(any(error['stage']=='source_entry' and '--main' in error['detail']
                            for error in manifest['errors']))
        self.assertTrue(any('not evidence of missing source' in warning for warning in manifest['warnings']))
        self.assertEqual(manifest['status'], 'review_required')
        self.assertEqual(manifest['mode'], 'pdf_fallback')
        self.assertTrue((output/'chinese_source_uncompiled.zip').is_file())
        self.assertIn('chinese_source_uncompiled.zip', manifest['artifacts'])

    def test_explicit_main_reaches_native_translation_for_multi_entry_source(self):
        adapter = FakeAdapter()
        def compile_fixture(project, entry, **kwargs):
            built = Path(project)/'fixture.pdf'
            make_pdf(built, chinese=True)
            return True, built, json.dumps({'success': True, 'layout_warnings': []})
        with patch.object(z, '_download', side_effect=self.downloaded(self.archive_bytes())), \
             patch.object(z, 'get_adapter', return_value=adapter), \
             patch.object(z, 'compile_latex_project', side_effect=compile_fixture) as compiler, \
             patch.object(pr, 'run_pdf_translation') as fallback:
            result, output, manifest = self.translate_query(main_tex='article.tex', no_fallback=True)
        fallback.assert_not_called()
        self.assertTrue(adapter.calls)
        self.assertEqual(compiler.call_count, 2)  # translation and delivered-ZIP rebuild
        self.assertEqual(manifest['mode'], 'latex_native')
        self.assertNotEqual(manifest['status'], 'failed')
        self.assertIs(manifest['source_acquisition']['source_available'], True)
        self.assertFalse(any(error['stage']=='source_entry' for error in manifest['errors']))
        self.assertTrue(manifest['archive_rebuild']['success'])
        self.assertTrue((output/'chinese_source.zip').is_file())

    def test_pdf_only_endpoint_remains_distinct_from_retrieval_failure_in_manifest(self):
        with patch.object(z, '_download', side_effect=self.downloaded(b'%PDF-1.7\nOnly PDF')), \
             patch.object(pr, 'run_pdf_translation', side_effect=self.fallback):
            result, _, manifest = self.translate_query()
        self.assertFalse(result)
        self.assertEqual(manifest['source_acquisition']['status'], 'endpoint_returned_pdf')
        self.assertIs(manifest['source_acquisition']['source_available'], False)
        self.assertFalse(any(error['stage']=='source_retrieval' for error in manifest['errors']))
        self.assertEqual(manifest['status'], 'review_required')


if __name__ == '__main__':
    unittest.main()
