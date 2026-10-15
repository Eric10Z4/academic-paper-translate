# Academic Paper Translate: a full-paper translation workflow for research reading

[中文](README.md) · [Hermes skill instructions](SKILL.md) · [Audit requirements](AUDIT_SPEC.md)

A Hermes skill for translating English academic papers into Simplified Chinese. Code version **2.2.0** prefers LaTeX source translation with local PDF compilation. When the native workflow is unavailable, it attempts PDF translation and requires visual review. After review passes, finalization removes generated sources and archives by default.

Inputs include arXiv IDs or links, English paper titles, local PDFs, and TeX project directories. Prompts request complete translations without summaries or reading guides.

## Project goals and engineering focus

The project connects original-paper retrieval, translation, structural protection, LaTeX compilation, and bilingual PDF delivery in a traceable workflow. Its engineering focus is formula and numeric integrity, source identity, explicit failure handling, and repeatable execution.

| Area | Purpose | Entry point |
| --- | --- | --- |
| Source identity and orchestration | Verifies local PDF candidates and coordinates native translation, fallback, and manifests | [zotero_translate.py](scripts/zotero_translate.py) |
| LaTeX protection | Separates translatable prose from formulas, citation keys, and complete numeric tokens | [latex_syntax.py](scripts/latex_syntax.py) |
| Provider adapters | Configures CPA, DeepSeek, and Ollama backends | [adapters](adapters/) |
| Delivery checks | Regression tests, source archive recompilation, and installed CLI checks | [tests](tests/), [audit requirements](AUDIT_SPEC.md) |

**Stack:** Python · PyMuPDF · LaTeX / XeLaTeX · LLM APIs · Hermes Skill · pdf2zh-next

## How it works

- **Source identity:** treats local PDF identifiers, citations, and filenames as candidates. Native source translation requires an identical official PDF or matching substantial text on every page; unverified candidates use the supplied PDF in the fallback workflow.
- **Source first:** extracts supported prose, headings, and captions in a working copy; protects math, table bodies, complete numeric tokens (including signs, decimals, and scientific notation), citation keys, and code; validates restored placeholders.
- **Local compilation:** runs XeLaTeX, with BibTeX or Biber when needed, and checks references and convergence. The delivered source ZIP is extracted and compiled again in a fresh directory.
- **Explicit fallback:** attempts pinned pdf2zh-next when source retrieval, native parsing, translation validation, or compilation fails. The overall job can still fail, including when no valid original PDF is available.
- **Bilingual PDF:** places original pages on the left and Chinese pages on the right, paired by page number. Unequal page counts retain all pages, with a notice on the missing side.
- **Reviewed delivery and cleanup:** Hermes inspects every Chinese page and compares formulas, fractions, and algorithms against the original. A review bound to all three PDF hashes enables removal of the current working copy and tracked archives, retaining PDFs, manifests, diagnostics, and translation caches. Original inputs remain unchanged.

The parser is not a complete TeX AST or macro expansion engine. It supports a limited set of structures; unsupported structures fail the native branch or trigger fallback. Source protection does not guarantee translation accuracy or identical layout for every paper.

## Requirements and installation

Recorded end-to-end validation used **Windows, Hermes, Python 3.13, MiKTeX XeLaTeX, and a local CPA endpoint**. Other platforms, Python versions, and model providers have not received equivalent live translation validation.

Prepare:

1. A dedicated Python environment with PyMuPDF from [requirements.txt](requirements.txt).
2. XeLaTeX, the paper's packages and fonts, and BibTeX / Biber as needed. The Windows workflow uses fonts including SimSun, SimHei, KaiTi, and FangSong.
3. uv on PATH for PDF fallback. The script launches **pdf2zh-next 2.9.0 / BabelDOC 0.6.2** in an isolated environment with bitstring<5.0.0. First use may download dependencies and model resources.
4. A working translation endpoint, model, and credentials.

~~~bash
git clone https://github.com/Eric10Z4/academic-paper-translate.git
cd academic-paper-translate

# Use the Python interpreter intended for this skill.
python -m pip install -r requirements.txt
python -m pip install uv
python -B scripts/zotero_translate.py --doctor
~~~

--doctor checks basic dependency and executable visibility. It does not validate API credentials, every package or font, or a complete PDF fallback run. MiKTeX automatic package installation is disabled; install identified missing dependencies before retrying.

You can also install a package built from this checkout:

~~~bash
python -m pip install ".[pdf]"
paper-translate --help
paper-translate --config "/absolute/path/to/config.json" --input "2201.02609" --output-dir "./output/2201.02609"
~~~

Packages include prompts and version resources, with VERSION as the version source. The pdf extra installs uv; the fallback engine still runs in its pinned isolated environment. Package users should keep private JSON outside site-packages and pass --config or ACADEMIC_TRANSLATE_CONFIG.

## Provider configuration

The default provider is cpa. Copy the JSON template and edit credentials locally:

~~~bash
cp config.example.json config.local.json
~~~

~~~json
{
  "providers": {
    "cpa": {
      "base_url": "http://127.0.0.1:8317/v1",
      "api_key": "YOUR_API_KEY",
      "model": "YOUR_MODEL",
      "timeout": 90,
      "attempts": 3
    }
  },
  "fallback": {
    "timeout": 1200,
    "no_proxy": "127.0.0.1,localhost"
  }
}
~~~

Replace placeholders with values supported by your service. The model in config.example.json is an existing deployment example, not a promise of availability from every provider. Do not commit credentials, private configuration, or backups containing secrets.

- CLI providers are cpa, deepseek, and ollama. Add a matching entry under providers, or use that provider's environment variables.
- CPA_API_KEY, CPA_BASE_URL, and CPA_MODEL override corresponding JSON values. Other providers use the DEEPSEEK_ or OLLAMA_ prefix.
- Configuration defaults to config.local.json in the skill root. Override it with --config /path/to/config.json or ACADEMIC_TRANSLATE_CONFIG.
- The program **does not read legacy config.yaml; the obsolete config.example.yaml has been removed** and has no --provider openai option. For another endpoint accepting the current Chat Completions request format, configure the cpa URL, key, and model.
- Set --workers, --prompt, and other workflow options through the CLI. The old YAML translation section has no effect.

## Usage

Run these examples from the repository root. In Hermes, use the explicit interpreter and absolute script path described below.

~~~bash
# An arXiv ID, full arXiv URL, or accurate English paper title.
python -B scripts/zotero_translate.py \
  --input "2201.02609" --output-dir "./output/2201.02609"

# Local TeX project, with an explicit entry point and original PDF.
python -B scripts/zotero_translate.py \
  --input "./paper_source" --main "main.tex" \
  --original "./paper.pdf" --output-dir "./output/paper" --workers 4

# Add translations beside an already downloaded original.pdf.
python -B scripts/zotero_translate.py \
  --input "./papers/example/original.pdf" --output-dir "./papers/example"
~~~

In-place PDF archiving requires an existing original.pdf to match the explicitly supplied original by SHA-256. Its contents and modification time are preserved. Different inputs, mismatched originals, and untracked translated artifacts are rejected; ordinary notes may remain. The output directory must not be the original TeX project root.

| Option | Purpose |
| --- | --- |
| --original PDF | Supply the original. Without one, a source-only input attempts compilation of the untranslated project for comparison, recording this provenance |
| --no-fallback | Stop if native translation fails |
| --workers 1..16 | Concurrency; default 4 |
| --compile-timeout 180 | Timeout in seconds per compilation subprocess, not for the whole workflow |
| --prompt cs_ai_specialized | Native prose prompt; alternatives are zotero_default and math_formula_preservation. PDF fallback uses a separate prompt |
| --finalize DIR --visual-review JSON | Finalize a delivery using a real visual review; mutually exclusive with input arguments |
| --keep-source | Retain tracked source archives during finalization; removed by default |
| --help | List all options |

--arxiv, --dir, and --pdf remain input aliases; choose only one input option. The old --output-zip option has been removed. Use --output-dir.

## Using Hermes

Place the skill in the **skills directory used by your Hermes installation**. The validated Windows installation uses %LOCALAPPDATA%/hermes/skills/academic-paper-translate; confirm the location for other installations.

The tested Hermes terminal uses Bash. This example invokes the translation environment without starting PowerShell:

~~~bash
PYTHON="$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"
SKILL_DIR="$LOCALAPPDATA/hermes/skills/academic-paper-translate"
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" --doctor
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" \
  --input "C:/papers/example/original.pdf" --output-dir "C:/papers/example"
~~~

Adjust paths to your installation. The translation environment can differ from Hermes's launcher interpreter. scripts/run.ps1 remains only for compatibility.

Ask Hermes to “use academic-paper-translate to translate this paper and inspect the result manifest.” Follow [SKILL.md](SKILL.md) to run long jobs in the background and wait for completion. If a previous process was interrupted, confirm that the process recorded in .translation/active.lock has exited before removing its stale lock and retrying.

## Outputs and status

Read **translation_manifest.json** in the output directory. The existence of a PDF alone does not establish success.

| Status | Meaning and artifacts |
| --- | --- |
| complete_native | Native programmatic checks and archive rebuild passed; inspect visual_review and cleanup and finish review/finalization before delivery |
| complete_fallback | The three PDFs passed a review bound to their current hashes and finalization completed; disclose PDF fallback and its limits |
| review_required | All PDF fallback results, plus native results with layout/font warnings; artifacts exist but acceptance is pending and the CLI returns nonzero |
| failed | Inspect the recorded stage and logs. Do not present older artifacts as this run's output |

Render and inspect every Chinese page, comparing formulas and algorithms by content rather than page number. Record actual observations using the [visual review schema](references/visual_review.md), then run:

~~~bash
python -B scripts/zotero_translate.py --finalize "./output/paper" --visual-review "./review.json"
~~~

Successful delivery requires `visual_review.status=passed` and `cleanup.status=complete`. By default, finalization removes the current run and hash-matched tracked source archives. Use `--keep-source` when source archives are requested. Failed or unreviewed runs retain diagnostics; original inputs, notes, unknown files, and older failed runs are not indiscriminately deleted. Use a separate output directory per paper.

## Validation and limits

- **v2.2: 152 local regression tests, 149 passed and 3 skipped for Windows link privileges.** Real Hermes validation covered a fraction fixture and the full SCORE paper: 246 validated segments, three 13-page PDFs, archive rebuild, and inspection of every Chinese page. Both native deliveries completed cleanup. See the [v2.2 validation record](docs/v2.2.0-formula-validation.md).

- The fixes following v2.1.1 recorded 92 passing deterministic tests, including source identity and complete numeric token protection. Those checks remain in the current suite.
- **v2.1: 86 deterministic regression tests passed; 7 Hermes end-to-end scenarios reached their expected outcomes**, covering native compilation, PDF fallback, safe macros, existing originals, and cached reruns. A direct CLI invocation was also verified through Hermes. See the [v2.1 report](docs/v2.1.0-修复与Hermes复验报告.md).
- v2.0 additionally checked constructed fixtures using CVPR, NeurIPS, ICML, and ACM styles, plus multi-page layouts. These were not full published papers reviewed sentence by sentence. The historical 62-paper collection was not rerun in full. See the [acceptance report](docs/学术论文翻译Skill修复与验收报告.md).
- Chinese text can change line breaks, fonts, float placement, and page counts. Pairing by page number is not semantic paragraph alignment. Identical layout is not guaranteed.
- Custom macros are checked only under supported rules. Long prose inside frozen macros remains untranslated. Arbitrary .sty/.cls definitions, dynamic TeX, and unknown structures are not guaranteed to work.
- **PDF-only formula reconstruction is not generally solved.** The live PDF-only fixture still split fractions and merged algorithm lines and must remain pending review. Stroke retention and heuristic risk-page hints do not prove formula fidelity or replace full-page inspection.
- Supported `looseness` integer assignments, accents, and conference metadata commands no longer force unnecessary fallback. Unknown dynamic syntax remains conservative. Algorithm bodies stay in the original language; only captions are translated. Network failures, unrecognized responses, and ambiguous entry files are not evidence that a paper lacks source.
- Bilingual composition attempts to transfer ordinary web links, internal jumps, and an outline. It does not guarantee every PDF annotation, action, or bookmark property.
- ZIP recompilation succeeds in the current environment; it does not establish universal portability or one-click Overleaf compatibility. TeX distributions, packages, and system fonts are not bundled.
- Automated checks cannot prove every sentence is accurate, complete, or terminologically consistent. Check critical passages before citing or relying on the translation.

## Tests and repository contents

~~~bash
# Deterministic tests; no live translation API required.
python -B -m unittest discover -s tests -p 'test_*.py' -v

# Run through Hermes. Requires configured CPA, compilation tools, and uv.
# This invokes the real translation service.
python -B tests/run_acceptance.py --workspace "/absolute/path/to/new-acceptance-workspace"
~~~

Use a new, isolated acceptance workspace and follow [AUDIT_SPEC.md](AUDIT_SPEC.md). Live translation counts refer to each version’s recorded validation. A passing PDF-only workflow test does not mean visual quality passed. CI covers deterministic regressions, builds, and installed CLI checks without calling live translation services.

scripts/ contains orchestration, syntax protection, compilation, and PDF fallback; providers are in adapters/, prompts in prompts/, tests in tests/, and historical reports in docs/. The companion-skills/ downloader can retrieve originals and sources separately; use the main entry point when translation is requested.

## Acknowledgments and license

Prompts draw on [Zotero PDF Translate](https://github.com/windingwind/zotero-pdf-translate). PDF fallback uses [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next). This project is not an official distribution of either project.

See [SECURITY.md](SECURITY.md) for credential and history cleanup guidance. Licensed under the [MIT License](LICENSE).
