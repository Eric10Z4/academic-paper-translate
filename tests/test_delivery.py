import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.delivery import finalize_delivery, CHECKS, PDFS
from scripts.project_utils import atomic_json, pdf_info, sha256
from test_regression import make_pdf


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.out=self.base/'out';self.out.mkdir()
        self.run=self.out/'.translation/runs'/('a'*32);self.run.mkdir(parents=True)
        (self.run/'main.tex').write_text('Generated working copy')
        (self.run/'engine.log').write_text('Diagnostic evidence')
        (self.out/'user_notes.tex').write_text('User source, never delete by extension')
        (self.out/'user.zip').write_bytes(b'user archive')
        (self.out/'.translation/cache.json').write_text('{}')
        for name in PDFS:make_pdf(self.out/name,chinese=name!='original.pdf')
        (self.out/'chinese_source.zip').write_bytes(b'tracked source archive')
        self.manifest={'status':'review_required','mode':'pdf_fallback','run_dir':str(self.run),
                       'artifacts':{name:pdf_info(self.out/name) for name in PDFS}}
        self.manifest['artifacts']['chinese_source.zip']={'sha256':sha256(self.out/'chinese_source.zip')}
        self.review={'reviewer':'test-fixture','notes':'Controlled test, no real visual claim',
                     'reviewed_pages':[1], 'checks':{name:'passed' for name in CHECKS},
                     'artifacts':{name:sha256(self.out/name) for name in PDFS}}
        self.review_path=self.base/'review.json'
        self.save()

    def tearDown(self):self.temp.cleanup()

    def save(self):
        atomic_json(self.out/'translation_manifest.json',self.manifest)
        atomic_json(self.review_path,self.review)

    def finalize(self,**kwargs):return finalize_delivery(self.out,self.review_path,**kwargs)

    def test_success_removes_only_managed_workspace_and_archive(self):
        original=(self.out/'original.pdf').read_bytes()
        stamp=(self.out/'original.pdf').stat().st_mtime_ns
        result=self.finalize()
        self.assertEqual(result['status'],'complete_fallback')
        self.assertFalse(self.run.exists())
        self.assertFalse((self.out/'chinese_source.zip').exists())
        self.assertEqual((self.out/'original.pdf').read_bytes(),original)
        self.assertEqual((self.out/'original.pdf').stat().st_mtime_ns,stamp)
        for name in ['user_notes.tex','user.zip','.translation/cache.json','visual_review.json']:
            self.assertTrue((self.out/name).exists())
        self.assertTrue((self.out/result['cleanup']['evidence_dir']/'engine.log').exists())

    def test_keep_source_is_explicit(self):
        self.finalize(keep_source=True)
        self.assertTrue((self.out/'chinese_source.zip').exists())
        self.assertFalse(self.run.exists())

    def test_verified_archive_from_previous_same_input_run_can_be_removed(self):
        self.manifest['prior_source_archives']={'chinese_source.zip':self.manifest['artifacts'].pop('chinese_source.zip')}
        self.save();self.finalize()
        self.assertFalse((self.out/'chinese_source.zip').exists())

    def test_changed_pdf_rejects_review_and_keeps_sources(self):
        make_pdf(self.out/'chinese_mono.pdf',pages=2,chinese=True)
        with self.assertRaisesRegex(ValueError,'PDF changed'):self.finalize()
        self.assertTrue(self.run.exists())

    def test_wrong_review_hash_is_rejected(self):
        self.review['artifacts']['chinese_mono.pdf']='old hash';self.save()
        with self.assertRaises(ValueError):self.finalize()
        self.assertTrue(self.run.exists())

    def test_failed_or_partial_inspection_cannot_complete(self):
        for change in ['check','pages','failed_run']:
            with self.subTest(change=change):
                self.review['checks']['inline_fractions']='failed' if change=='check' else 'passed'
                self.review['reviewed_pages']=[] if change=='pages' else [1]
                self.manifest['status']='failed' if change=='failed_run' else 'review_required'
                self.save()
                with self.assertRaises(ValueError):self.finalize()
                self.assertTrue((self.run/'main.tex').exists())

    def test_escaped_run_path_is_never_deleted(self):
        victim=self.base/'source';victim.mkdir();(victim/'main.tex').write_text('input')
        self.manifest['run_dir']=str(victim);self.save()
        with self.assertRaisesRegex(ValueError,'owned'):self.finalize()
        self.assertTrue((victim/'main.tex').exists())

    def test_changed_or_untracked_archive_is_preserved(self):
        (self.out/'chinese_source.zip').write_bytes(b'user replacement')
        with self.assertRaisesRegex(ValueError,'archive'):self.finalize()
        self.assertTrue(self.run.exists())
        self.assertEqual((self.out/'chinese_source.zip').read_bytes(),b'user replacement')

    def test_active_translation_blocks_cleanup(self):
        (self.out/'.translation/active.lock').write_text('existing')
        with self.assertRaisesRegex(ValueError,'active'):self.finalize()
        self.assertTrue(self.run.exists())
        self.assertEqual((self.out/'.translation/active.lock').read_text(),'existing')

    def test_symlink_in_run_rejected(self):
        victim=self.base/'input.tex';victim.write_text('original')
        try:(self.run/'linked.tex').symlink_to(victim)
        except OSError:self.skipTest('Symlink privilege is unavailable')
        with self.assertRaisesRegex(ValueError,'links'):self.finalize()
        self.assertEqual(victim.read_text(),'original')

    def test_finalize_is_repeatable(self):
        self.finalize()
        result=self.finalize()
        self.assertEqual(result['cleanup']['status'],'complete')
        self.assertEqual(result['cleanup']['removed'],[])

    def test_atomic_json_does_not_follow_predictable_temp_link(self):
        target=self.base/'record.json';outside=self.base/'outside.txt';outside.write_text('original')
        old_temp=self.base/'record.json.tmp'
        try:old_temp.symlink_to(outside)
        except OSError:self.skipTest('Symlink privilege is unavailable')
        atomic_json(target,{'safe':True})
        self.assertEqual(outside.read_text(),'original')
        self.assertEqual(json.loads(target.read_text()),{'safe':True})

    def test_evidence_link_cannot_redirect_copy(self):
        destination=self.out/'.translation/evidence'/self.run.name
        destination.mkdir(parents=True)
        outside=self.base/'outside.txt';outside.write_text('original')
        try:(destination/'engine.log').symlink_to(outside)
        except OSError:self.skipTest('Symlink privilege is unavailable')
        with self.assertRaisesRegex(ValueError,'links'):self.finalize()
        self.assertTrue(self.run.exists())
        self.assertEqual(outside.read_text(),'original')

    def test_evidence_hard_link_cannot_redirect_copy(self):
        destination=self.out/'.translation/evidence'/self.run.name
        destination.mkdir(parents=True)
        outside=self.base/'outside.txt';outside.write_text('original')
        try:os.link(outside,destination/'engine.log')
        except OSError:self.skipTest('Hard links are unavailable')
        with self.assertRaisesRegex(ValueError,'hard links'):self.finalize()
        self.assertTrue(self.run.exists())
        self.assertEqual(outside.read_text(),'original')


if __name__=='__main__':unittest.main()
