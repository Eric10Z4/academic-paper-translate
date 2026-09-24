# Academic Paper Translate (学术论文原格式精准翻译)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/CVPR%20%7C%20ICCV-Verified-blue?style=flat-square" alt="Conference Verified" />
  <img src="https://img.shields.io/badge/Zotero-Prompt%20Aligned-red?style=flat-square" alt="Zotero Aligned" />
</p>

专门针对学术顶会论文（CVPR / ICCV / NeurIPS / ICML 等）打造的**全篇完整、精准、保留原始双栏排版与 LaTeX 数学公式**的高质量翻译工具箱。

---

## 💡 为什么需要这个项目？

目前绝大部分大模型翻译论文存在以下致命痛点：
1. **胡乱总结与自我发挥**：经常自作主张输出大纲、解析、摘要或长篇废话，而不是用户需要的逐句纯翻译；
2. **排版格式彻底崩溃**：双栏论文在机器翻译后，断行错乱、左栏大面积留白、标题与段落倒错；
3. **数学公式与符号乱码**：行内公式（`$...$`）和矩阵公式环境被翻译模型污染篡改；
4. **学术专有名词不地道**：机器翻译生硬，无法达到如 Zotero 划词翻译插件的学术语境深度。

**本项目通过两项核心工程方案彻底解决上述问题：**
- **方案 A（LaTeX 源码逐段精翻）**：一键拉取 arXiv 源码，按自然段切分并并发调用 **Zotero 原版学术提示词**，数学公式与交叉引用 100% 原位冻结，自动注入中文支持并打包，直接在 Overleaf 上一键重编译出出版级原生双栏 PDF。
- **方案 B（PDF 版面级双栏镜像对照）**：基于底层文档版面分析引擎，自动输出**纯中文排版版（Mono PDF）**与**中英双语左右镜像对照版（Dual PDF）**。

---

## ✨ 核心特性

- 🎯 **零解析、零解读、零总结**：严格 1:1 逐句精准翻译，绝不掺杂任何对话式解释或大纲。
- 📐 **100% 格式与公式保留**：所有数学符号、表格结构、矢量图与文献引用（`\cite`、`\ref`）完好无损。
- 📝 **内置 Zotero 官方插件原版提示词**：直接复用科研界最认可的学术 Prompt，专有名词（如“广义类别发现”、“对比表征学习”、“半监督 $k$-means”）精准规范。
- ⚡ **逐段独立并发请求（Paragraph-by-Paragraph）**：将全文拆分为自然段落并发请求，避免长文本导致的上下文漂移与术语变形。
- 🔌 **多后端适配器支持**：内置开箱即用的 DeepSeek（V3 / R1）、OpenAI（GPT-4o-mini 等）以及本地 Ollama 离线适配器。
- 🤖 **Hermes Agent 技能即插即用**：提供标准 `SKILL.md`，可直接作为 AI Agent 的 procedural skill 使用。

---

## 📂 项目结构

```text
academic-paper-translate/
├── SKILL.md                          # Hermes Agent 技能规范
├── README.md                         # 中文说明文档
├── README_EN.md                      # 英文说明文档
├── LICENSE                           # MIT 开源协议
├── pyproject.toml                    # 构建配置
├── requirements.txt                  # 依赖包列表
├── config.example.yaml               # 配置文件模板
├── prompts/                          # 提示词库
│   ├── zotero_default.txt            # Zotero 原版学术提示词
│   ├── cs_ai_specialized.txt         # 计算机视觉与机器学习专用提示词
│   └── math_formula_preservation.txt # 重度数学公式保护提示词
├── adapters/                         # 模型适配器
│   ├── base.py                       # 基础适配器抽象类
│   ├── deepseek_adapter.py           # DeepSeek 官方适配器
│   ├── openai_adapter.py             # 标准 OpenAI 兼容适配器
│   └── ollama_adapter.py             # 本地 Ollama 离线适配器
├── scripts/                          # 核心执行脚本
│   ├── zotero_translate.py           # 核心统一命令行工具
│   └── pdf_runner.py                 # PDF 版面分析调用器
└── companion-skills/                 # 适配与联动技能
    └── arxiv-paper-downloader/       # arXiv 论文与源码下载适配器
```

---

## 🚀 快速上手

### 1. 环境安装

推荐使用 `uv` 极速安装，也可使用传统 `pip`：

```bash
# 克隆仓库
git clone https://github.com/Eric10Z4/academic-paper-translate.git
cd academic-paper-translate

# 安装基础依赖
pip install -r requirements.txt

# 若需要直接处理本地 PDF，安装 PDF 扩展
pip install pdf2zh-next
```

### 2. 配置模型后端

复制配置模板：
```bash
cp config.example.yaml config.yaml
```
根据需要修改 `config.yaml`。默认填写 DeepSeek API Key（性价比极高）或 OpenAI API Key。也可以直接通过环境变量传递：
```bash
export DEEPSEEK_API_KEY="your-api-key"
```

---

## 📖 使用示例

### 场景 1：arXiv 论文一键逐段精翻（最推荐，100% 顶会原排版）
只需输入 arXiv 编号，脚本会自动下载官方源码、逐段调用学术 Prompt 精翻、注入中文宏包并打包为 ZIP：
```bash
python scripts/zotero_translate.py --arxiv "2201.02609" --provider deepseek --output-zip "GCD_paper_zh.zip"
```
> **交付物**：生成的 `GCD_paper_zh.zip` 直接上传到 [Overleaf](https://www.overleaf.com) 点击 Recompile，即可获得完美的矢量级中文双栏顶会论文！

### 场景 2：已有本地 LaTeX 工程批量翻译
```bash
python scripts/zotero_translate.py --dir "./my_paper_source" --provider deepseek --output-zip "./translated_source.zip"
```

### 场景 3：本地 PDF 自动化版面翻译（生成中英对照 PDF）
```bash
python scripts/zotero_translate.py --pdf "./sample_paper.pdf" --output-dir "./output"
```
自动生成两份文件：
- `sample_paper.zh-CN.mono.pdf`（纯中文原版面 PDF）
- `sample_paper.zh-CN.dual.pdf`（中英双语左右镜像对照 PDF）

---

## 🛠️ 作为 Hermes Agent Skill 使用

本项目根目录提供了完全符合 Hermes 规范的 `SKILL.md`。
可以直接将本目录复制或软链接至你的 Hermes Skills 目录：

```bash
# Windows
xcopy /E /I academic-paper-translate %LOCALAPPDATA%\hermes\skills\academic-paper-translate

# Linux / macOS
cp -r academic-paper-translate ~/.local/share/hermes/skills/
```

在对话中直接唤醒：
> *“帮我用 academic-paper-translate 翻译这篇论文：https://arxiv.org/abs/2211.11727”*

---

## 🤝 致谢与参考

- [Zotero PDF Translate](https://github.com/windingwind/zotero-pdf-translate) - 提供了极高质量的学术翻译提示词模板。
- [PDFMathTranslate (pdf2zh)](https://github.com/PDFMathTranslate/PDFMathTranslate) / [pdf2zh-next](https://github.com/pdf2zh-next) - 提供了卓越的 PDF 双栏与数学公式版面分析能力。

---

## 📄 开源许可证

本项目采用 [MIT License](LICENSE) 开源协议。
