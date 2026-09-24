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
- 📐 **100% Math & Layout Preservation**: Preserves all equations, tables, figures, and `\cite` / `\ref` cross-references.
- 📝 **Zotero Official Prompt Aligned**: Reuses the proven academic translation prompt from Zotero PDF Translate.
- ⚡ **Paragraph-by-Paragraph Concurrency**: Prevents context drift and term deformation by translating natural paragraphs in parallel.
- 🔌 **Pluggable Backends**: Out-of-the-box adapters for CPA (Gemini 3.8 Flash High), DeepSeek (V3/R1), OpenAI, and local Ollama.
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

#### 1. One-click arXiv Paper Translation (Recommended)
```bash
python scripts/zotero_translate.py --arxiv "2201.02609" --output-zip "GCD_paper_zh.zip"
```
Upload `GCD_paper_zh.zip` to Overleaf and click **Recompile** for native, publication-grade dual-column output!

#### 2. Local LaTeX Project Translation
```bash
python scripts/zotero_translate.py --dir "./my_paper_source" --output-zip "./translated_source.zip"
```

#### 3. Direct PDF Translation (Bilingual Side-by-Side)
```bash
python scripts/zotero_translate.py --pdf "./paper.pdf" --output-dir "./output"
```

---

## 📊 Token Usage Benchmark (Real-world Data)

Tested on top-tier conference papers using `gemini-3.8-flash-high`:

| Paper | Scope | Chunks | Prompt Tokens | Completion Tokens | Reasoning Tokens | Total Tokens |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **GCD (CVPR 2022)** | 10 Pages (Main + Refs) | 153 | 42,387 | 15,374 | ~106,400 | **~164K** |
| **SimGCD (ICCV 2023)** | 15 Pages (Main + Supp + Figures) | 545 | 106,006 | 31,929 | ~261,800 | **~400K** |

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
