"""Bounded recovery for the observed XeTeX/microtype font conflict."""
import json
from pathlib import Path
from unittest.mock import patch
from test_regression import Case, lc, make_pdf


CONFLICT = 'main.tex:73: Cannot\nuse XeTeXglyph with ptmr8c; not a native platform font.\nMT@get@char@unit ... XeTeXglyph'


class MicrotypeCompilerTests(Case):
    def successful_pass(self, cwd):
        cwd=Path(cwd)
        (cwd/'main.aux').write_text('Stable auxiliary data',encoding='utf-8')
        make_pdf(cwd/'main.pdf')
        return 0,'Successful XeTeX pass'

    def test_injection_is_idempotent_and_after_template_packages(self):
        source='% \\begin{document} is only a comment\n'+r'\documentclass{article}\usepackage{PRIMEarxiv}\usepackage{microtype}\begin{document}$\frac{a}{b}$\end{document}'
        root=self.project(source,wrap=False);entry=root/'main.tex'
        lc.inject_microtype_protrusion_compatibility(entry)
        once=entry.read_bytes()
        lc.inject_microtype_protrusion_compatibility(entry)
        self.assertEqual(entry.read_bytes(),once)
        text=entry.read_text(encoding='utf-8')
        self.assertEqual(text.count(lc.MICROTYPE_BEGIN),1)
        self.assertGreater(text.index(lc.MICROTYPE_BEGIN),text.index(r'\usepackage{microtype}'))
        self.assertLess(text.index(lc.MICROTYPE_BEGIN),text.rindex(r'\begin{document}'))
        self.assertIn(r'$\frac{a}{b}$',text)
        self.assertNotIn(r'\setmainfont',text)

    def test_precise_failure_retries_in_isolation_and_persists_only_success(self):
        root=self.project(r'The result is $\frac{a}{b}$.');entry=root/'main.tex'
        before=entry.read_bytes();seen=[]
        def execute(cmd,cwd,timeout,env,logfile):
            text=(Path(cwd)/'main.tex').read_text(encoding='utf-8')
            self.assertEqual(entry.read_bytes(),before)
            seen.append(Path(cwd).name)
            if lc.MICROTYPE_BEGIN not in text:return 1,CONFLICT
            self.assertIn(r'\microtypesetup{protrusion=false}',text)
            return self.successful_pass(cwd)
        with patch.object(lc.shutil,'which',return_value='xelatex'),patch.object(lc,'_run',side_effect=execute):
            ok,pdf,summary=lc.compile_latex_project(root)
        self.assertTrue(ok);self.assertTrue(Path(pdf).is_file())
        self.assertEqual(seen,['ctex','ctex_microtype','ctex_microtype','ctex_microtype'])
        report=json.loads(Path(json.loads(summary)['report']).read_text(encoding='utf-8'))
        self.assertEqual(report['selected_mode'],'ctex_microtype')
        self.assertTrue(report['attempts'][-1]['microtype_protrusion_disabled'])
        self.assertEqual(entry.read_text(encoding='utf-8').count(lc.MICROTYPE_BEGIN),1)
        self.assertIn(r'$\frac{a}{b}$',entry.read_text(encoding='utf-8'))
        # A subsequent independent build already has the repair in its source.
        with patch.object(lc.shutil,'which',return_value='xelatex'),patch.object(lc,'_run',side_effect=lambda cmd,cwd,timeout,env,logfile:self.successful_pass(cwd)):
            ok,_,summary=lc.compile_latex_project(root)
        self.assertTrue(ok)
        report=json.loads(Path(json.loads(summary)['report']).read_text(encoding='utf-8'))
        self.assertEqual(len(report['attempts']),1)
        self.assertEqual(entry.read_text(encoding='utf-8').count(lc.MICROTYPE_BEGIN),1)

    def test_same_error_after_repair_stops_without_modifying_source(self):
        root=self.project('The template cannot compile.');entry=root/'main.tex';before=entry.read_bytes()
        with patch.object(lc.shutil,'which',return_value='xelatex'),patch.object(lc,'_run',return_value=(1,CONFLICT)) as run:
            ok,pdf,summary=lc.compile_latex_project(root)
        self.assertFalse(ok);self.assertIsNone(pdf)
        # One compatibility retry per existing Chinese engine configuration.
        self.assertEqual(run.call_count,4)
        self.assertEqual(entry.read_bytes(),before)
        report=json.loads(Path(json.loads(summary)['report']).read_text(encoding='utf-8'))
        self.assertEqual([a['mode'] for a in report['attempts']],['ctex','ctex_microtype','xecjk','xecjk_microtype'])

    def test_unrelated_errors_do_not_trigger_protrusion_repair(self):
        errors=[
            'Cannot use XeTeXglyph with ptmr8c; not a native platform font.',
            'MT@get@char@unit\nUndefined control sequence.',
            '! Missing character in font ptmr8c.',
            "! LaTeX Error: File `microtype.sty' not found.",
        ]
        for error in errors:
            root=self.project('A different compile failure.');before=(root/'main.tex').read_bytes()
            with self.subTest(error=error),patch.object(lc.shutil,'which',return_value='xelatex'),patch.object(lc,'_run',return_value=(1,error)) as run:
                ok,pdf,summary=lc.compile_latex_project(root,chinese=False)
                self.assertFalse(ok);self.assertIsNone(pdf);self.assertEqual(run.call_count,1)
                report=json.loads(Path(json.loads(summary)['report']).read_text(encoding='utf-8'))
                self.assertFalse(report['attempts'][0]['microtype_protrusion_disabled'])
                self.assertEqual((root/'main.tex').read_bytes(),before)

    def test_existing_repair_is_not_reapplied_to_mask_a_persistent_error(self):
        root=self.project('The repaired template still fails.');entry=root/'main.tex'
        lc.inject_microtype_protrusion_compatibility(entry);before=entry.read_bytes()
        with patch.object(lc.shutil,'which',return_value='xelatex'),patch.object(lc,'_run',return_value=(1,CONFLICT)) as run:
            ok,_,_=lc.compile_latex_project(root,chinese=False)
        self.assertFalse(ok);self.assertEqual(run.call_count,1)
        self.assertEqual(entry.read_bytes(),before)

    def test_font_recovery_retains_the_protrusion_fix(self):
        root=self.project('A template needs both documented repairs.')
        def execute(cmd,cwd,timeout,env,logfile):
            text=(Path(cwd)/'main.tex').read_text(encoding='utf-8')
            if lc.MICROTYPE_BEGIN not in text:return 1,CONFLICT
            if lc.FONT_BEGIN not in text:return 0,"LaTeX Font Warning: Font shape `TU/ptm/m/n' undefined"
            return self.successful_pass(cwd)
        with patch.object(lc.shutil,'which',return_value='xelatex'),patch.object(lc,'_run',side_effect=execute):
            ok,_,summary=lc.compile_latex_project(root)
        self.assertTrue(ok)
        report=json.loads(Path(json.loads(summary)['report']).read_text(encoding='utf-8'))
        self.assertEqual(report['selected_mode'],'ctex_legacyfonts_microtype')
        translated=(root/'main.tex').read_text(encoding='utf-8')
        self.assertIn(lc.FONT_BEGIN,translated);self.assertIn(lc.MICROTYPE_BEGIN,translated)
