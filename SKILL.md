---
name: academic-paper-translate
description: Use when translating papers to Chinese with layout.
---

# Academic Paper Translate (学术论文原格式精准翻译)

针对顶会学术论文（PDF / LaTeX 源码 / arXiv）进行**全篇完整、精准、保留原始学术排版与数学公式**的高质量翻译。

## 核心守则（极其重要）
- **零解析、零解读、零总结**：绝不生成大纲、背景介绍、要点提炼或长文评述。只做纯翻译。
- **100% 格式保留**：保留双栏排版、页码、图表位置，所有 LaTeX 数学公式和特殊符号原封不动。
- **逐段请求（Paragraph-by-Paragraph）保障最高质量**：严格将文章切分成独立的自然段落，单段单独请求模型，保证专有名词与学术行文质量与 Zotero 划词划段完全一致。
- **统一使用 Zotero 插件原版学术提示词**。

---

## 1. Zotero 官方插件原版提示词（Prompt Template）
直接复用用户本地 Zotero PDF Translate 插件中生效的 Prompt：

```text
As an academic expert with specialized knowledge in various fields, please provide a proficient and precise translation from English to Simplified Chinese of the academic text enclosed in 🔤. It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. Keep all LaTeX markup, math notation ($...$, equations), citations (\cite{...}), references (\ref{...}), and environment tags intact. Translate only the natural language text. The text is as follows:

🔤 {source_text} 🔤

Please provide the translated result without any additional explanation and remove 🔤.
```

---

## 2. 标准化执行工作流

### 模式 A：arXiv / LaTeX 源码工程一键精翻（推荐，100% 出版级排版）
```bash
python scripts/zotero_translate.py \
  --arxiv "<arXiv编号，如 2201.02609>" \
  --provider deepseek \
  --output-zip "<输出包名.zip>"
```

### 模式 B：纯本地 PDF 自动保排版翻译（使用 pdf2zh-next + Zotero 提示词）
```bash
python scripts/zotero_translate.py \
  --pdf "<本地PDF绝对路径>" \
  --output-dir "<输出目录>"
```
