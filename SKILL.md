---
name: academic-paper-translate
description: Use when translating papers to Chinese with layout.
---

# Academic Paper Translate (学术论文原格式精准翻译)

专门针对学术论文（arXiv / LaTeX 源码 / PDF）进行全篇完整、精准、保留原始学术排版与数学公式的高质量翻译。

## 核心守则（极其重要）
- 零解析、零解读、零总结：绝不生成大纲、背景介绍、要点提炼或长文评述。用户只要求纯翻译。
- 100% 格式保留：保留双栏排版、页码、图表位置，所有 LaTeX 数学公式和特殊符号原封不动。
- 表格与数据绝对冻结（最高准则）：表格环境（tabular/table）内的所有实验数据、对比数值、方法名、指标列一律 100% 原样保留，绝不允许大模型触碰与篡改，仅翻译 \caption 表题！
- 优先寻找 LaTeX 源码工程包（强制优先级）：凡是论文翻译任务，第一优先级必须自动在全网（arXiv 等）寻找下载 LaTeX 源码包；只有在实在检索不到可用源码时，才允许降级采用纯 PDF 版面翻译模式。
- 统一使用 Zotero 插件原版学术提示词。

---

## 1. Zotero 官方插件原版提示词（Prompt Template）
直接复用 Zotero PDF Translate 插件中生效的 Prompt：

```text
As an academic expert with specialized knowledge in various fields, please provide a proficient and precise translation from English to Simplified Chinese of the academic text enclosed in 🔤. It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. Keep all LaTeX markup, math notation ($...$, equations), citations (\cite{...}), references (\ref{...}), and environment tags intact. Translate only the natural language text. The text is as follows:

🔤 {source_text} 🔤

Please provide the translated result without any additional explanation and remove 🔤.
```

---

## 2. 模型与网络环境配置
- 多后端支持：支持 CPA (本地反代/Gemini)、DeepSeek (官方API)、OpenAI 兼容端点、本地 Ollama 离线模型。
- 本地反代/CPA 典型配置：
  - API Endpoint: http://127.0.0.1:8317/v1
  - Model: gemini-3.8-flash-high (或 deepseek-chat)
  - API Key: 通过环境变量（如 CPA_API_KEY / DEEPSEEK_API_KEY）或命令行参数传入
- 避坑环境设置：如本地存在代理转发，建议设置 `NO_PROXY=127.0.0.1,localhost`，绕过系统代理或本地端口回环导致的 502。

---

## 3. 标准化执行工作流（优先级管线）

### 第一优先级（方案 1）：自动检索 LaTeX 源码工程一键精翻（出版级排版，表格 100% 冻结无损）
无论提供的是论文标题、arXiv 链接还是本地英文 PDF，脚本均会自动提取 arXiv 编号或向 arXiv API 发起标题检索，自动下载官方 e-print 源码包解压精翻。

#### 执行命令（全自动入口）：
```bash
NO_PROXY=127.0.0.1,localhost python scripts/zotero_translate.py \
  --input "<arXiv编号 / 论文完整英文标题 / 本地PDF路径 / 本地TeX源码目录>" \
  --provider deepseek \
  --output-dir "<输出目录>" \
  --workers 4
```

- 表格处理逻辑：脚本自动识别所有 table、table*、tabular、tabularx、longtable 环境，内部所有数值、对齐符号、宏命令全部原封不动冻结，仅提取其中的 \caption{...} 进行中文翻译；
- 公式与代码保护：自动识别 equation、align、gather、algorithm、lstlisting 等环境，绝不送往大模型；
- 中文宏包注入：主文档自动检测并注入 \usepackage[UTF8]{ctex}，并打包生成 Overleaf 标准工程 ZIP 包。

---

### 第二优先级（方案 2）：纯本地 PDF 自动保排版翻译（降级兜底方案）
只有在全网检索确认没有公开 LaTeX 源码包（如非 arXiv 封闭会议/期刊扫描件）时，才允许降级使用该模式。

```bash
NO_PROXY=127.0.0.1,localhost uv tool run --from pdf2zh-next pdf2zh_next \
  "<本地PDF路径>" \
  --openaicompatible \
  --openai-compatible-base-url "http://127.0.0.1:8317/v1" \
  --openai-compatible-api-key "your-api-key" \
  --openai-compatible-model "gemini-3.8-flash-high" \
  --no-auto-extract-glossary \
  --figure-table-protection-threshold 0.1 \
  --qps 5 \
  --lang-in en --lang-out zh-CN \
  --custom-system-prompt "As an academic expert with specialized knowledge in various fields, please provide a proficient and precise translation from English to Simplified Chinese of the academic text. It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. Please provide the translated result without any additional explanation." \
  --output "<输出目录>"
```

- 显式配置 `--figure-table-protection-threshold 0.1`，最大限度降低表格区域被误切送译的概率；
- 默认生成 `_mono.pdf`（纯中文单语）与 `_dual.pdf`（中英双语对照）。

---

## 4. 论文集标准化归档规范（三 PDF 体系）

在建立或扩充论文集目录（如 openworld CV、agent、经典 等）时，统一遵循以下标准化归档流程：

### 1. 目录结构规范
每个主题论文集为一个大文件夹，根目录下维护 README.md 导读清单；每篇论文单独建一个编号子文件夹：

```text
<论文集根目录>/
├── README.md                                          # 论文集全景路线图与导读索引
└── [两位序号]_[论文核心名称]_[会议年份或arXiv]/
    ├── original.pdf       # 官方原版英文论文 PDF
    ├── chinese_mono.pdf   # 100% 保留双栏排版、高清图表与数学公式的纯中文版 PDF
    └── bilingual_dual.pdf # 左右 1:1 镜像并列的中英双语对照版 PDF
```

### 2. 标准文件命名要求（严格一致）
- original.pdf：官方原版英文论文；
- chinese_mono.pdf：纯中文单语论文（双栏排版、公式代码、表格完全对齐）；
- bilingual_dual.pdf：中英双语左右对照版 PDF。

### 3. README.md 索引维护规范
归档后同步在根目录的 README.md 中更新论文导读项，包含完整标题、作者与机构、发表平台/年份、子文件夹路径、以及核心创新点。
