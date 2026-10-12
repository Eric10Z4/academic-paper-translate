"""Conservative TeX text extraction. Unknown syntax fails closed, never guessed.

Only explicitly selected prose spans are editable. Every command, formula,
number, comment and frozen environment is kept outside model-controlled text.
The same environment stack follows static input/include edges across files.
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path


class IntegrityError(ValueError):
    pass


TABLE_ENVS = set('table table* tabular tabular* tabularx tabulary longtable supertabular xltabular longtblr tblr'.split())
TABLE_ENVS.update('sidewaystable sidewaystable* threeparttable threeparttablex longtable*'.split())
MATH_ENVS = set('equation equation* align align* alignat alignat* gather gather* multline multline* eqnarray eqnarray* displaymath math flalign flalign* split cases matrix pmatrix bmatrix smallmatrix'.split())
MATH_ENVS.update('aligned alignedat array subequations dmath dmath*'.split())
CODE_ENVS = set('verbatim Verbatim lstlisting minted algorithm algorithm* algorithmic algorithmicx algorithm2e'.split())
CODE_ENVS.update('verbatim* BVerbatim SaveVerbatim filecontents filecontents*'.split())
FIGURE_ENVS={'figure','figure*','wrapfigure','sidewaysfigure','sidewaysfigure*','teaserfigure'}
FROZEN_ENVS = TABLE_ENVS | MATH_ENVS | CODE_ENVS | FIGURE_ENVS | {'thebibliography', 'tikzpicture'}
PROSE_ENVS=set('document abstract itemize enumerate description theorem lemma proof proposition corollary definition remark example solution quotation quote center flushleft flushright minipage strip adjustwidth multicols landscape samepage acknowledgments acknowledgements ack appendix appendices icmlauthorlist subfigure subtable theorem* proof* lemma* assumption fact observation notation claim property'.split())
TEXT_ARGS = {x: {0} for x in 'title subtitle section subsection subsubsection paragraph subparagraph chapter part caption footnote footnotetext thanks textbf textit textsl textsc textrm textsf texttt textnormal emph underline mbox MakeUppercase MakeLowercase subfloat'.split()}
TEXT_ARGS.update({'href': {1}, 'textcolor': {1}, 'colorbox': {1}, 'fcolorbox': {2}, 'captionof': {1}, 'foreignlanguage': {1}, 'texorpdfstring': {0, 1}})
TEXT_OPTIONALS = {'title', 'section', 'subsection', 'subsubsection', 'chapter', 'part', 'caption', 'captionof'}
TEXT_ARGS.update({'icmltitle':{0},'icmltitlerunning':{0},'keywords':{0}})
OPAQUE = set('label ref eqref pageref autoref vref cref Cref nameref url path includegraphics input include bibliography bibliographystyle addbibresource printbibliography documentclass usepackage RequirePackage author date institute affiliation email address keywords hypersetup geometry setlength addtolength setcounter addtocounter newcommand renewcommand providecommand DeclareRobustCommand newenvironment renewenvironment def gdef edef xdef let newtheorem theoremstyle definecolor color vspace hspace rule cline cmidrule multicolumn multirow resizebox scalebox graphicspath lstinputlisting includepdf index nomenclature SI si num qty unit phantom hphantom vphantom'.split())
NOARGS = set('maketitle tableofcontents clearpage newpage pagebreak noindent indent par item appendix centering raggedright raggedleft hfill vfill small footnotesize scriptsize tiny large Large LARGE huge Huge normalsize today TeX LaTeX LaTeXe relax protect leavevmode and quad qquad ldots dots medskip bigskip smallskip topsep toprule midrule bottomrule hline textwidth linewidth columnwidth columnsep baselineskip textheight fill begingroup endgroup bfseries itshape normalfont rmfamily sffamily ttfamily selectfont'.split())
NOARGS.update({'vskip','hskip'})
OPAQUE.add('nocite')
OPAQUE.update('icmlauthor icmlaffiliation icmlcorrespondingauthor icmlsetsymbol printAffiliationsAndNotice icmlEqualContribution'.split())
TOKEN_RE = re.compile(r'§LATEX_REF_\d+§')
COMMAND_RE = re.compile(r'\\([A-Za-z@]+|[^\r\n])\*?')
LETTERS = re.compile(r'[A-Za-z]{3,}')


def command_at(text, pos):
    m = COMMAND_RE.match(text, pos)
    if not m:
        raise IntegrityError(f'Invalid command at offset {pos}')
    return m.group(1), m.end()


def balanced(text, start, opening='{', closing='}'):
    """Return the exclusive end; escaped delimiters and comments do not count."""
    if start >= len(text) or text[start] != opening:
        raise IntegrityError('Expected balanced group')
    depth, i = 1, start + 1
    while i < len(text):
        c = text[i]
        if c == '\\':
            _, i = command_at(text, i)
            continue
        if c == '%':
            end = text.find('\n', i)
            i = len(text) if end < 0 else end + 1
            continue
        # Braced content inside an optional argument can contain literal ].
        if opening == '[' and c == '{':
            i = balanced(text, i)
            continue
        if c == opening: depth += 1
        if c == closing: depth -= 1
        i += 1
        if depth == 0: return i
    raise IntegrityError(f'Unclosed {opening} group at offset {start}')


def arguments(text, start, limit=None):
    args, p, curly = [], start, 0
    while p < len(text):
        q = p
        while q < len(text) and text[q] in ' \t\r\n': q += 1
        if q >= len(text) or text[q] not in '[{': break
        op = text[q]
        if limit is not None and op == '{' and curly >= limit: break
        end = balanced(text, q, op, '}' if op == '{' else ']')
        args.append((op, q, end))
        if op == '{': curly += 1
        p = end
    return args, p


def escape_prose(value):
    # Models occasionally emit already escaped literal characters.
    value = re.sub(r'\\([%&#_$\{\}])', r'\1', value)
    escapes = {'\\': r'\textbackslash{}', '%': r'\%', '&': r'\&', '#': r'\#', '_': r'\_', '$': r'\$', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(escapes.get(c, c) for c in value)


def unmask_latex_tokens(text, mapping, escape=False):
    if not isinstance(text, str) or not text.strip():
        raise IntegrityError('Empty translation')
    expected = list(mapping)
    actual = TOKEN_RE.findall(text)
    if actual != expected or '§LATEX' in TOKEN_RE.sub('', text):
        raise IntegrityError('Placeholder missing, duplicated, changed, unknown or reordered')
    if not escape:
        for token, raw in mapping.items(): text = text.replace(token, raw)
        return text
    result, p = [], 0
    for m in TOKEN_RE.finditer(text):
        result.extend([escape_prose(text[p:m.start()]), mapping[m.group()]])
        p = m.end()
    result.append(escape_prose(text[p:]))
    return ''.join(result)


def mask_latex_tokens(text):
    if '§LATEX_REF_' in text: raise IntegrityError('Reserved placeholder occurs in source')
    mapping, chunks, i, last = {}, [], 0, 0
    while i < len(text):
        if text[i] != '\\': i += 1; continue
        name, end = command_at(text, i)
        if name.startswith('cite') or name in {'ref', 'eqref', 'pageref', 'label', 'url', 'cref', 'Cref', 'autoref', 'nameref'}:
            _, end = arguments(text, end)
            token = f'§LATEX_REF_{len(mapping)}§'
            mapping[token] = text[i:end]
            chunks.extend([text[last:i], token]); last = end
        i = end
    chunks.append(text[last:])
    return ''.join(chunks), mapping


@dataclass
class Segment:
    path: Path
    start: int
    end: int
    raw: str
    masked: str
    mapping: dict
    kind: str = 'prose'

    @property
    def key(self):
        return hashlib.sha256((self.kind+'\0'+self.masked+'\0'+self.raw).encode()).hexdigest()

    def restore(self, answer):
        answer = answer.strip()
        if re.match(r'^(以下是|译文[：:]|翻译[：:]|Here is|Translation:)', answer, re.I):
            raise IntegrityError('Model returned commentary')
        plain = TOKEN_RE.sub('', answer)
        if not re.search(r'[\u3400-\u9fff]', plain):
            raise IntegrityError('No Chinese translation was returned')
        source_plain = TOKEN_RE.sub('', self.masked)
        if len(plain) > max(100, len(source_plain)*5):
            raise IntegrityError('Translation is unexpectedly expanded')
        restored = unmask_latex_tokens(answer, self.mapping, escape=True)
        left = self.raw[:len(self.raw)-len(self.raw.lstrip())]
        right = self.raw[len(self.raw.rstrip()):]
        return left + restored + right


@dataclass
class State:
    active: bool = False
    envs: list = field(default_factory=list)

    @property
    def frozen(self): return any(e in FROZEN_ENVS for e in self.envs)


class ProjectPlan:
    def __init__(self, root, main):
        self.root, self.main = Path(root).resolve(), Path(main).resolve()
        self.sources, self.segments, self.issues = {}, [], []
        self.contexts, self.visiting = {}, set()
        self.prose_envs=PROSE_ENVS.copy()
        self.literal_macros=set()
        self._keys = set()
        self.state = State()
        self._file(self.main, self.state)
        if self.state.envs:
            raise IntegrityError('Unclosed environments: '+', '.join(self.state.envs))
        self.segments.sort(key=lambda s: (str(s.path), s.start))
        for a, b in zip(self.segments, self.segments[1:]):
            if a.path == b.path and a.end > b.start:
                raise IntegrityError('Overlapping editable spans')
        if self.issues: raise IntegrityError('; '.join(sorted(set(self.issues))))

    def _file(self, path, state):
        path = path.resolve()
        if not path.is_relative_to(self.root): raise IntegrityError('Include escapes project directory')
        if path in self.visiting: raise IntegrityError('Recursive include: '+path.name)
        if path.is_symlink(): raise IntegrityError('Symbolic link in source project')
        context = (state.active, tuple(state.envs))
        if path in self.contexts and self.contexts[path] != context:
            raise IntegrityError('File reused in incompatible contexts: '+path.name)
        self.contexts[path] = context
        raw = path.read_bytes()
        try: text = raw.decode('utf-8')
        except UnicodeDecodeError as e: raise IntegrityError('Source must be valid UTF-8: '+path.name) from e
        if '§LATEX_REF_' in text:
            raise IntegrityError('Reserved placeholder occurs in source: '+path.name)
        self.sources[path] = text
        self.visiting.add(path)
        self._scan(path, text, 0, len(text), state)
        self.visiting.remove(path)

    def _scan(self, path, text, start, stop, state, kind='prose'):
        parts = []  # (start, end, is_prose)

        def flush():
            if not parts: return
            lo, hi = parts[0][0], parts[-1][1]
            prose = ''.join(text[a:b] for a,b,is_text in parts if is_text)
            if LETTERS.search(prose):
                mapping, buf = {}, []
                for a,b,is_text in parts:
                    raw=text[a:b]
                    if is_text: buf.append(raw)
                    else:
                        token=f'§LATEX_REF_{len(mapping)}§';mapping[token]=raw;buf.append(token)
                masked=''.join(buf).strip()
                if '§LATEX_REF_' in prose: raise IntegrityError('Reserved placeholder in source')
                key=(path,lo,hi)
                if key not in self._keys:
                    self._keys.add(key)
                    self.segments.append(Segment(path,lo,hi,text[lo:hi],masked,mapping,kind))
            parts.clear()

        def emit(a,b,plain=False):
            if a==b: return
            if parts and parts[-1][1] != a: flush()
            parts.append((a,b,plain))

        i=start
        while i<stop:
            c=text[i]
            enabled=state.active and not state.frozen
            if c=='%':
                end=text.find('\n',i,stop);end=stop if end<0 else end+1
                flush();i=end;continue
            if c=='$' or text.startswith(('\\(', '\\['),i):
                delim='$$' if text.startswith('$$',i) else c if c=='$' else text[i:i+2]
                closing={'\\(':'\\)','\\[':'\\]'}.get(delim,delim)
                p=i+len(delim)
                while p<stop:
                    if text.startswith(closing,p): break
                    if text[p]=='%':
                        line_end=text.find('\n',p,stop);p=stop if line_end<0 else line_end+1;continue
                    if text[p]=='\\': _,p=command_at(text,p)
                    else:p+=1
                if p>=stop: raise IntegrityError('Unclosed math at '+path.name)
                end=p+len(closing)
                if enabled:emit(i,end)
                i=end;continue
            if c=='\\':
                name,end=command_at(text,i)
                if name in {'verb','lstinline'}:
                    delim=text[end:end+1]
                    p=text.find(delim,end+1,stop) if delim else -1
                    if p<0:raise IntegrityError('Unclosed inline verbatim')
                    if enabled:emit(i,p+1)
                    i=p+1;continue
                if name in {'begin','end'}:
                    args,argend=arguments(text,end,limit=1)
                    groups=[a for a in args if a[0]=='{']
                    if not groups:raise IntegrityError('Environment without name')
                    _,a,b=groups[0];env=text[a+1:b-1]
                    flush()
                    if name=='begin':
                        if enabled and env not in FROZEN_ENVS|self.prose_envs:
                            raise IntegrityError('Unknown environment '+env+'; no safe text rule is defined')
                        state.envs.append(env)
                        if env=='document':state.active=True
                        if env in {'verbatim','verbatim*','Verbatim','BVerbatim','SaveVerbatim','lstlisting','minted','filecontents','filecontents*'}:
                            match=re.search(r'\\end\s*\{'+re.escape(env)+r'\}',text[argend:stop])
                            if not match:raise IntegrityError('Unclosed code environment')
                            i=argend+match.end();state.envs.pop();continue
                    else:
                        if not state.envs or state.envs[-1]!=env:raise IntegrityError('Unbalanced environment '+env)
                        state.envs.pop()
                        if env=='document':state.active=False
                    i=argend;continue
                if name in {'input','include'}:
                    flush();args,argend=arguments(text,end,limit=1)
                    groups=[a for a in args if a[0]=='{']
                    if groups:
                        _,a,b=groups[0];target=text[a+1:b-1].strip();end=argend
                    else:
                        m=re.match(r'\s*([^\s%{}]+)',text[end:stop])
                        if not m:raise IntegrityError('Missing include target')
                        target=m.group(1);end+=m.end()
                    if re.search(r'[\\#$]',target):raise IntegrityError('Dynamic include requires explicit source expansion')
                    rel=Path(target)
                    if not rel.suffix:rel=rel.with_suffix('.tex')
                    choices=[path.parent/rel,self.root/rel,self.main.parent/rel]
                    child=next((p for p in choices if p.is_file()),None)
                    if child is None:raise IntegrityError('Missing included source: '+target)
                    self._file(child,state);i=end;continue
                if name in {'twocolumn','onecolumn'}:
                    flush();args,argend=arguments(text,end,limit=0)
                    if enabled:
                        for op,a,b in args:self._scan(path,text,a+1,b-1,State(active=True),kind='column_header')
                    i=argend;continue
                is_caption=name in {'caption','captionof'}
                allowed=(enabled or (is_caption and state.active and any(e in TABLE_ENVS|FIGURE_ENVS for e in state.envs)) or (name in {'title','subtitle','icmltitlerunning','keywords'} and not state.active))
                if name in TEXT_ARGS and allowed:
                    flush();args,argend=arguments(text,end,limit=max(TEXT_ARGS[name])+1)
                    n=0
                    for op,a,b in args:
                        selected=(op=='{' and n in TEXT_ARGS[name]) or (op=='[' and name in TEXT_OPTIONALS)
                        if selected:self._scan(path,text,a+1,b-1,State(active=True),kind='caption' if is_caption else name)
                        if op=='{':n+=1
                    i=argend;continue
                if name.startswith('cite') or name in OPAQUE:
                    args,argend=arguments(text,end)
                    if name in {'newcommand','renewcommand','providecommand','DeclareRobustCommand'}:
                        groups=[(a,b) for op,a,b in args if op=='{']
                        if len(groups)>=2:
                            macro=text[groups[0][0]+1:groups[0][1]-1]
                            defined=re.fullmatch(r'\\([A-Za-z]+)',macro)
                            if defined:
                                defined=defined.group(1);self.literal_macros.discard(defined)
                                body=text[groups[-1][0]+1:groups[-1][1]-1]
                                if not any(op=='[' for op,_,_ in args) and re.fullmatch(r'[A-Za-z0-9 .,;:!?-]+',body):
                                    self.literal_macros.add(defined)
                    if name=='newtheorem':
                        groups=[(a,b) for op,a,b in args if op=='{']
                        if groups:self.prose_envs.add(text[groups[0][0]+1:groups[0][1]-1])
                    if enabled:emit(i,argend)
                    i=argend;continue
                if name in NOARGS or not name.isalpha():
                    if enabled:emit(i,end)
                    i=end;continue
                # An unknown zero-argument macro can open a table or math mode.
                # Accept only definitions proven to expand to plain literal text.
                args,argend=arguments(text,end)
                if enabled:
                    if name not in self.literal_macros or args:
                        self.issues.append(f'Unknown macro \\{name} in {path.name}; add an explicit safe rule or expand it first')
                    emit(i,argend)
                i=argend;continue
            if not enabled:
                flush();i+=1;continue
            if c in '{}~&#^_':emit(i,i+1);i+=1;continue
            if c.isdigit():
                m=re.match(r'\d+(?:[.,]\d+)*',text[i:stop]);end=i+len(m.group())
                emit(i,end);i=end;continue
            end=i+1
            while end<stop and text[end] not in '\\%${}~&#^_' and not text[end].isdigit():end+=1
            chunk=text[i:end]
            # Blank lines and sentence boundaries bound request size while
            # environment state remains global and independent of paragraphs.
            for m in re.finditer(r'\r?\n[ \t]*\r?\n|(?<=[.!?])\s+(?=[A-Z])',chunk):
                q=i+m.start();emit(i,q,True);flush();i+=m.end();chunk=text[i:end]
                break
            else:
                if end-i>1600:
                    cut=text.rfind(' ',i,i+1600)
                    if cut>i: end=cut+1
                emit(i,end,True);i=end
                if parts and parts[-1][1]-parts[0][0]>=1600:flush()
        flush()

    def apply(self, translations):
        updated={}
        for path,source in self.sources.items():
            spans=[s for s in self.segments if s.path==path]
            cursor=0;chunks=[]
            for s in spans:
                if s.key not in translations:raise IntegrityError('Missing translated segment')
                chunks.extend([source[cursor:s.start],s.restore(translations[s.key])]);cursor=s.end
            chunks.append(source[cursor:]);updated[path]=''.join(chunks)
        return updated
