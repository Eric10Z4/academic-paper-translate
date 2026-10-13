# Academic Paper Translate

[中文](README.md) · [Hermes skill instructions](SKILL.md) · [Audit requirements](AUDIT_SPEC.md)

A Hermes skill for translating English academic papers into Simplified Chinese. Code version **2.1.1** prefers LaTeX source translation with local PDF compilation. When the native workflow is unavailable, it attempts PDF translation and records the fallback explicitly.

Inputs include arXiv IDs or links, English paper titles, local PDFs, and TeX project directories. Prompts request complete translations without summaries or reading guides.

## How it works

- **Source first:** extracts supported prose, headings, and captions in a working copy; protects math, table bodies, numbers, citation keys, and code; validates restored placeholders.
- **Local compilation:** runs XeLaTeX, with BibTeX or Biber when needed, and checks references and convergence. The delivered source ZIP is extracted and compiled again in a fresh directory.
- **Explicit fallback:** attempts pinned pdf2zh-next when source retrieval, native parsing, translation validation, or compilation fails. The overall job can still fail, including when no valid original PDF is available.
- **Bilingual PDF:** places original pages on the left and Chinese pages on the right, paired by page number. Unequal page counts retain all pages, with a notice on the missing side.
- **Traceable runs:** retains a manifest, working copies, logs, and validated translation caches. The same input can resume; the original TeX project is not modified.

The parser is not a complete TeX AST or macro expansion engine. It supports a limited set of structures; unsupported structures fail the native branch or trigger fallback. Source protection does not guarantee translation accuracy or identical layout for every paper.

## Requirements and installation

Recorded end-to-end validation used **Windows, Hermes, Python 3.13, MiKTeX XeLaTeX, and a local CPA endpoint**. Other platforms, Python versions, and model providers have not received equivalent live translation validation.

Prepare:

1. A dedicated Python environment with PyMuPDF from [requirements.txt](requirements.txt).
2. XeLaTeX, the paper's packages and fonts, and BibTeX / Biber as needed. The Windows workflow uses fonts including SimSun, SimHei, KaiTi, and FangSong.
3. uv on PATH for PDF fallback. The script launches **pdf2zh-next 2.9.0** in an isolated environment with bitstring<5.0.0. First use may download dependencies and model resources.
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
| complete_native | original.pdf, chinese_mono.pdf, bilingual_dual.pdf, and chinese_source.zip; native checks and extracted ZIP recompilation passed |
| complete_fallback | The three standard PDFs, plus chinese_source_uncompiled.zip if an unfinished source archive was produced. Disclose PDF fallback |
| review_required | Artifacts exist, but layout or font warnings require inspection; the CLI returns a nonzero status |
| failed | Inspect the recorded stage and logs. Do not present older artifacts as this run's output |

.translation/ stores working copies and caches. Use a separate output directory per paper. Review logs and manifests for local paths and paper content before sharing. An uncompiled archive may contain original or partially processed source and is not proof of complete Chinese source.

## Validation and limits

- **v2.1: 86 deterministic regression tests passed; 7 Hermes end-to-end scenarios reached their expected outcomes**, covering native compilation, PDF fallback, safe macros, existing originals, and cached reruns. A direct CLI invocation was also verified through Hermes. See the [v2.1 report](docs/v2.1.0-修复与Hermes复验报告.md).
- v2.0 additionally checked constructed fixtures using CVPR, NeurIPS, ICML, and ACM styles, plus multi-page layouts. These were not full published papers reviewed sentence by sentence. The historical 62-paper collection was not rerun in full. See the [acceptance report](docs/学术论文翻译Skill修复与验收报告.md).
- Chinese text can change line breaks, fonts, float placement, and page counts. Pairing by page number is not semantic paragraph alignment. Identical layout is not guaranteed.
- Custom macros are checked only under supported rules. Long prose inside frozen macros remains untranslated. Arbitrary .sty/.cls definitions, dynamic TeX, and unknown structures are not guaranteed to work.
- PDF fallback disables table-text translation and enables figure/table protection, but layout recognition cannot provide TeX source-level integrity guarantees.
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

Use a new, isolated acceptance workspace and follow [AUDIT_SPEC.md](AUDIT_SPEC.md). Translation counts above refer to recorded v2.1 validation, not a continuous integration badge. v2.1.1 additionally checks builds, installed resources and CLI entry points. CI does not call live translation services.

scripts/ contains orchestration, syntax protection, compilation, and PDF fallback; providers are in adapters/, prompts in prompts/, tests in tests/, and historical reports in docs/. The companion-skills/ downloader can retrieve originals and sources separately; use the main entry point when translation is requested.

## Acknowledgments and license

Prompts draw on [Zotero PDF Translate](https://github.com/windingwind/zotero-pdf-translate). PDF fallback uses [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next). This project is not an official distribution of either project.

See [SECURITY.md](SECURITY.md) for credential and history cleanup guidance. Licensed under the [MIT License](LICENSE).

## Source identity and numeric integrity

Local PDF identifiers are candidates only. Native source translation requires an identical official PDF or identical substantial extracted text on every page. Unavailable or unverified candidates fall back to the supplied PDF; the manifest records the decision. Signed decimals and scientific notation are protected as complete tokens. The regression suite covers foreign-paper citations, filename candidates, unavailable references, and dropped-sign translations.
