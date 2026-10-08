# Academic Paper Translate

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/CVPR%20%7C%20ICCV-Verified-blue?style=flat-square" alt="Conference Verified" />
  <img src="https://img.shields.io/badge/Zotero-Prompt%20Aligned-red?style=flat-square" alt="Zotero Aligned" />
</p>

A specialized academic translation toolkit for top-tier computer science and scientific papers (CVPR, ICCV, NeurIPS, ICML, etc.), delivering **complete, precise translations while preserving 100% of two-column layouts and LaTeX mathematical notations**.

---

## 💡 Why This Project?

Most generic AI translation tools fail on scientific papers:
1. **Unwanted Summaries**: They invent outlines, takeaways, or conversational commentary instead of providing exact sentence-by-sentence translations.
2. **Broken Layouts**: Dual-column formatting breaks, leaving huge gaps or inverted paragraphs.
3. **Mangled Math**: Inline formulas (`$...$`) and matrix environments get corrupted.
4. **Poor Terminology**: Translations sound awkward and lack rigorous academic depth.

**Academic Paper Translate solves this via two robust engineering pipelines:**
- **Pipeline A (LaTeX Source Translation)**: Downloads official arXiv source packages, translates paragraph-by-paragraph with official **Zotero academic prompts**, keeps all math and citations byte-for-byte intact, injects CTEX Chinese support, and outputs an Overleaf-ready ZIP.
- **Pipeline B (Direct PDF Dual-Column Mirror)**: Uses document layout analysis to generate both **monolingual Chinese PDFs** and **bilingual side-by-side mirror PDFs**.

---

## ✨ Features

- 🎯 **Zero Fluff**: Strictly 1:1 translation with no unsolicited summaries or chatting.
- 📐 **100% Math & Layout Preservation**: Preserves all equations, tables, figures, and `\cite` / `
ef` cross-references.
- 📊 **Table & Experimental Data Freeze (Highest Priority)**: Numerical values, metric columns, and benchmark names in tables are 100% untouched; only `\caption` is translated.
- 🔍 **Auto arXiv Source Pipeline**: Resolves arXiv IDs from PDF text or titles, downloads e-print packages, and falls back to PDF layout translation if source is unavailable.
- 📝 **Zotero Official Prompt Aligned**: Reuses the proven academic translation prompt from Zotero PDF Translate.
- ⚡ **Paragraph-by-Paragraph Concurrency**: Prevents context drift and term deformation by translating natural paragraphs in parallel.
- 🔌 **Pluggable Backends**: Out-of-the-box adapters for DeepSeek (V3/R1), CPA (Local Proxy/Gemini), OpenAI (GPT-4o-mini), and local Ollama.
- 📚 **Standardized Three-PDF Archive**: Systematically organizes `original.pdf`, `chinese_mono.pdf`, `bilingual_dual.pdf` alongside index READMEs.
- 🤖 **Hermes Agent Ready**: Includes native `SKILL.md` for AI agent workflows.

---

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/Eric10Z4/academic-paper-translate.git
cd academic-paper-translate
pip install -r requirements.txt
pip install pdf2zh-next  # Optional, for direct PDF processing
```

### Usage Examples

#### 0. Auto Pipeline (Recommended)
Pass an arXiv ID, paper title, or local PDF directly:
```bash
python scripts/zotero_translate.py --input "2201.02609" --provider deepseek --output-dir "./output"
```

#### 1. One-click arXiv Paper Translation
```bash
python scripts/zotero_translate.py --arxiv "2201.02609" --provider deepseek --output-zip "GCD_paper_zh.zip"
```
Upload `GCD_paper_zh.zip` to Overleaf and click **Recompile** for native, publication-grade dual-column output!

#### 2. Local LaTeX Project Translation
```bash
python scripts/zotero_translate.py --dir "./my_paper_source" --provider deepseek --output-zip "./translated_source.zip"
```

#### 3. Direct PDF Translation (Bilingual Side-by-Side)
```bash
python scripts/zotero_translate.py --pdf "./paper.pdf" --output-dir "./output"
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
