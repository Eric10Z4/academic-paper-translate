"""Native formula and algorithm regressions; no network or model calls."""
from test_regression import Case, FakeAdapter, z
from scripts.latex_syntax import ALGORITHM_ENVS, IntegrityError, ProjectPlan, TOKEN_RE


class NativePlanCase(Case):
    def plan(self, body, definitions=''):
        source = '\\documentclass{article}\n'+definitions+'\n\\begin{document}\n'+body+'\n\\end{document}'
        root = self.project(source, wrap=False)
        (root/'main.tex').write_bytes(source.encode('utf-8'))
        return root, ProjectPlan(root, root/'main.tex')


class NativeFormulaTests(NativePlanCase):
    def test_nested_inline_fractions_are_single_opaque_atoms(self):
        formulas = [
            r'$s_j(x)=-\frac{x_j-f_j(\text{pa}_j(x))}{\sigma_j^2}$',
            r'$\text{Var}\left(\frac{\partial s_j(x)}{\partial x_j}\right)=0$',
            r'\(\dfrac{\frac{a}{b}}{1+\frac{c}{d}}\)',
            r'\ensuremath{\tfrac{\partial s_j(X)}{\partial x_j}}',
        ]
        root, plan = self.plan('The results are '+', followed by '.join(formulas)+'.')
        atoms = [raw for segment in plan.segments for raw in segment.mapping.values()]
        for formula in formulas:
            self.assertEqual(atoms.count(formula), 1)
        requests = '\n'.join(segment.masked for segment in plan.segments)
        for hidden in [r'\frac', r'\dfrac', r'\tfrac', r'\partial', 'sigma_j']:
            self.assertNotIn(hidden, requests)
        adapter = FakeAdapter()
        z.process_latex_project(root, adapter)
        translated = (root/'main.tex').read_text(encoding='utf-8')
        for formula in formulas:
            self.assertIn(formula, translated)

    def test_fraction_with_comment_and_escaped_dollar_is_not_split(self):
        formula = '$\\frac{a}{b}% comment contains $ and \\)\n+\\text{cost \\$1}$'
        root, plan = self.plan('A paragraph contains '+formula+' and remains readable.')
        self.assertIn(formula, [raw for segment in plan.segments for raw in segment.mapping.values()])
        z.process_latex_project(root, FakeAdapter())
        self.assertIn(formula, (root/'main.tex').read_text(encoding='utf-8'))

    def test_large_inline_formula_is_not_cut_at_request_boundary(self):
        formula = '$'+r'\frac{a}{b}+'*200+'1$'
        _, plan = self.plan('The complete expression is '+formula+' and it is fixed.')
        self.assertIn(formula, [raw for segment in plan.segments for raw in segment.mapping.values()])
        self.assertFalse(any(r'\frac' in segment.masked for segment in plan.segments))

    def test_ensuremath_does_not_consume_following_independent_prose_group(self):
        _, plan = self.plan(r'The result \ensuremath{\frac{a}{b}} {Important independent prose} is given.')
        self.assertTrue(any('Important independent prose' in s.masked for s in plan.segments))

    def test_unclosed_math_and_ungrouped_ensuremath_are_rejected(self):
        for formula in [r'$\frac{a}{b}', r'\(\frac{a}{b}', r'\ensuremath\frac{a}{b}']:
            with self.subTest(formula=formula), self.assertRaises(IntegrityError):
                self.plan('The expression '+formula)

    def test_formula_placeholder_loss_or_reordering_cannot_write_source(self):
        for answer in ['中文内容', '中文§LATEX_REF_1§§LATEX_REF_0§', '中文§LATEX_REF_0§§LATEX_REF_0§']:
            root, _ = self.plan(r'The fractions are $\frac{a}{b}$ and $\frac{c}{d}$.')
            before = (root/'main.tex').read_bytes()
            with self.subTest(answer=answer), self.assertRaises(IntegrityError):
                z.process_latex_project(root, FakeAdapter(lambda text: answer))
            self.assertEqual((root/'main.tex').read_bytes(), before)


class IntegerAssignmentTests(NativePlanCase):
    def test_looseness_assignment_is_complete_and_hidden(self):
        for assignment in [r'\looseness=-1', r'\looseness = +1', r'\looseness 0', r'\looseness0', r'\looseness - 1', '\\looseness% comment\n= -1']:
            with self.subTest(assignment=assignment):
                root, plan = self.plan(assignment+'Many causal algorithms maximize a loss function.')
                self.assertEqual(plan.segments[0].mapping, {'§LATEX_REF_0§': assignment})
                self.assertNotIn('looseness', plan.segments[0].masked)
                self.assertNotIn('-1', plan.segments[0].masked)
                z.process_latex_project(root, FakeAdapter(lambda text: ''.join(TOKEN_RE.findall(text))+'2026年的方法采用此目标。'))
                translated = (root/'main.tex').read_text(encoding='utf-8')
                self.assertIn(assignment+r'\relax 2026年的方法', translated)

    def test_looseness_terminates_before_adjacent_frozen_number(self):
        root, _ = self.plan(r'\looseness=-1Many methods use 2026 samples.')
        z.process_latex_project(root, FakeAdapter(lambda text: ''.join(TOKEN_RE.findall(text))+'个样本用于训练。'))
        translated = (root/'main.tex').read_text(encoding='utf-8')
        self.assertIn(r'\looseness=-1\relax 2026', translated)
        self.assertNotIn(r'\looseness=-12026', translated)

    def test_unsupported_integer_expressions_fail_before_translation(self):
        for assignment in [r'\looseness=\numexpr1+2\relax', r'\looseness=\count0', r'\looseness=1.5', r'\looseness=1+2', r'\looseness=１２', r'\looseness=']:
            root = self.project(assignment+'Many methods are described.')
            adapter = FakeAdapter()
            with self.subTest(assignment=assignment), self.assertRaises(IntegrityError):
                z.process_latex_project(root, adapter)
            self.assertEqual(adapter.calls, [])

    def test_unsafe_redefinition_of_integer_primitive_is_not_whitelisted(self):
        with self.assertRaises(IntegrityError):
            self.plan(r'\looseness=-1Many methods are described.', r'\def\looseness{\begin{table}}')


class AlgorithmCaptionTests(Case):
    def test_every_algorithm_environment_only_exposes_caption(self):
        for env in sorted(ALGORITHM_ENVS):
            with self.subTest(env=env):
                program = '\n'+r'\STATE SecretProgram $\frac{\partial s_j(X)}{\partial x_j}$'+'\n'+r'\FOR {$k=1,\ldots,d$}'+'\n'+r'\STATE nodes $\leftarrow$ nodes $\setminus\{l\}$'+'\n'+r'\ENDFOR'+'\n'
                body = '\\begin{'+env+'}[t]\n'+r'\caption[Brief algorithm title]{SCORE matching causal order search $\frac{a}{b}$}\label{alg:score}'+program+'\\end{'+env+'}\nFollowing prose.'
                root, adapter, _, _ = self.translate(body)
                requests = '\n'.join(adapter.calls)
                self.assertIn('SCORE matching causal order search', requests)
                self.assertIn('Brief algorithm title', requests)
                self.assertNotIn('SecretProgram', requests)
                self.assertNotIn(r'\frac', requests)
                self.assertNotIn('nodes', requests)
                translated = (root/'main.tex').read_text(encoding='utf-8')
                self.assertIn(program, translated)
                self.assertIn(r'\label{alg:score}', translated)
                self.assertIn(r'$\frac{a}{b}$', translated)

    def test_nested_algorithmic_and_static_includes_remain_frozen(self):
        program = r'\STATE HiddenInput $\frac{a}{b}$'+'\n'+r'\FOR {$k=1,\ldots,d$}\STATE KeepThis\ENDFOR'
        body = r'\begin{algorithm}\caption{Search for the causal order}\begin{algorithmic}\input{steps}\end{algorithmic}\end{algorithm}'
        root, adapter, _, before = self.translate(body, {'steps.tex': program})
        self.assertEqual((root/'steps.tex').read_bytes(), before[root/'steps.tex'])
        self.assertTrue(any('Search for the causal order' in request for request in adapter.calls))
        self.assertFalse(any('HiddenInput' in request or 'KeepThis' in request for request in adapter.calls))

    def test_captionof_algorithm_and_verbatim_are_distinguished(self):
        code = r'\begin{verbatim}\caption{Hidden literal caption}\end{verbatim}'
        root, adapter, _, _ = self.translate(code+r'\begin{algorithmic}\captionof{algorithm}{A visible algorithm title}\STATE SecretProgram\end{algorithmic}')
        self.assertIn(code, (root/'main.tex').read_text(encoding='utf-8'))
        requests = '\n'.join(adapter.calls)
        self.assertIn('A visible algorithm title', requests)
        self.assertNotIn('Hidden literal caption', requests)
        self.assertNotIn('SecretProgram', requests)

    def test_explicit_keywords_prose_is_translated_without_opening_unknown_macros(self):
        source = r'\documentclass{article}\icmlkeywords{Causal discovery, score matching}\begin{document}\begin{keywords}Learning causal graphs\end{keywords}\end{document}'
        _, adapter, _, _ = self.translate(source, wrap=False)
        requests = '\n'.join(adapter.calls)
        self.assertIn('Causal discovery, score matching', requests)
        self.assertIn('Learning causal graphs', requests)
        with self.assertRaises(IntegrityError):
            self.translate(r'The unknown \H{Important prose} remains unsupported.')

    def test_aistats_metadata_is_frozen_but_titles_and_acknowledgements_translate(self):
        author = r'\aistatsauthor{Author Alpha \And Author Beta}'
        address = r'\aistatsaddress{Private Institute \\ contact@example.org \And Another Institute}'
        source = r'\documentclass{article}\runningtitle{Learning from demonstrations}\begin{document}\twocolumn[\aistatstitle{A reduction to online learning}'+author+address+r']\acks{We thank the research team.}\end{document}'
        root, adapter, _, _ = self.translate(source, wrap=False)
        requests = '\n'.join(adapter.calls)
        for prose in ['Learning from demonstrations', 'A reduction to online learning', 'We thank the research team']:
            self.assertIn(prose, requests)
        for opaque in ['Author Alpha', 'Private Institute', 'contact@example.org']:
            self.assertNotIn(opaque, requests)
        translated = (root/'main.tex').read_text(encoding='utf-8')
        self.assertIn(author, translated)
        self.assertIn(address, translated)

    def test_redefined_metadata_wrapper_cannot_hide_structure(self):
        source = r'\documentclass{article}\def\acks#1{\input{private}}\begin{document}\acks{Visible prose}\end{document}'
        root=self.project(source,wrap=False)
        adapter=FakeAdapter()
        with self.assertRaises(IntegrityError):
            z.process_latex_project(root,adapter)
        self.assertEqual(adapter.calls,[])


class TextCommandCompatibilityTests(NativePlanCase):
    def test_double_acute_accent_and_single_letter_are_frozen_together(self):
        accents = [r'\H{o}', r'\H{O}', r'\H u', '\\H% comment\n{o}']
        for accent in accents:
            with self.subTest(accent=accent):
                root, plan = self.plan('The graph follows Erd'+accent+'s random model.')
                self.assertIn(accent, [raw for s in plan.segments for raw in s.mapping.values()])
                self.assertFalse(any(r'\H' in s.masked for s in plan.segments))
                z.process_latex_project(root,FakeAdapter())
                self.assertIn(accent,(root/'main.tex').read_text(encoding='utf-8'))

    def test_accent_requires_a_literal_single_letter(self):
        for accent in [r'\H{Hidden prose}',r'\H{\unknown}',r'\H\unknown',r'\H{}',r'\H{1}']:
            with self.subTest(accent=accent),self.assertRaises(IntegrityError):
                self.plan('The graph uses '+accent+' in its label.')

    def test_redefined_accent_is_not_blindly_whitelisted(self):
        for definition in [r'\def\H#1{\begin{table}}',r'\def\H{\input{private}}']:
            with self.subTest(definition=definition),self.assertRaises(IntegrityError):
                self.plan(r'The graph uses Erd\H{o}s labels.',definition)

    def test_text_outside_math_is_translated_but_math_text_is_frozen(self):
        formula=r'$X_i=\text{MLP}(\text{PA}_i)+\frac{a}{b}$'
        root,plan=self.plan('The equation is '+formula+r', where \text{Multi-Layer Perceptron} {Independent prose} is specified.')
        requests='\n'.join(s.masked for s in plan.segments)
        self.assertIn('Multi-Layer Perceptron',requests)
        self.assertIn('Independent prose',requests)
        self.assertNotIn('PA',requests)
        self.assertNotIn(r'\frac',requests)
        z.process_latex_project(root,FakeAdapter())
        self.assertIn(formula,(root/'main.tex').read_text(encoding='utf-8'))

    def test_text_redefinition_still_requires_a_safe_proof(self):
        with self.assertRaises(IntegrityError):
            self.plan(r'The method \text{Visible description} is defined.',r'\def\text#1{\input{private}}')
