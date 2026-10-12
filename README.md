# Academic Paper Translate

[English](README_EN.md) · [Hermes 技能说明](SKILL.md) · [核验规范](AUDIT_SPEC.md)

面向 Hermes 的英文学术论文全文翻译技能。当前代码版本为 **2.1.1**：优先翻译 LaTeX 源码并在本地编译中文 PDF；原生流程不可用时尝试 PDF 翻译，并在结果记录中明确标注降级。

支持 arXiv 编号或链接、英文论文标题、本地 PDF 和 TeX 工程目录。翻译目标为简体中文，要求模型只输出译文，不生成摘要或论文导读。

## 工作方式

- **源码优先**：在工作副本中提取受支持的正文、标题和 caption，冻结公式、表格正文、数值、引用键和代码，检查占位符是否完整恢复。
- **本地编译与核验**：采用 XeLaTeX，按需调用 BibTeX 或 Biber，检查引用及编译收敛；源码 ZIP 还会解压到新目录重新编译。
- **明确降级**：找不到可用源码，或原生解析、翻译校验、编译失败时，尝试固定版本的 pdf2zh-next。没有有效原 PDF 时仍可能失败。
- **双语 PDF**：原文在左、中文在右，按页码配对；页数不同时保留全部页面，并在缺页侧标注说明。
- **可追踪运行**：保留清单、工作副本、日志和已验证译文缓存。相同输入可续跑；原始 TeX 工程不被修改。

解析器不是完整的 TeX AST 或宏展开器。它只支持部分已知结构；未知或无法证明安全的结构会导致原生分支失败或降级。源码保护也不等于所有真实论文的语义和排版均已获得保证。

## 环境与安装

已完成的端到端验收基于 **Windows、Hermes、Python 3.13、MiKTeX XeLaTeX 和本地 CPA**。其他平台、Python 版本及模型后端尚未完成同等范围的真实翻译验收。

准备以下组件：

1. 专用 Python 环境，安装 [requirements.txt](requirements.txt) 中的 PyMuPDF。
2. XeLaTeX、论文需要的宏包和字体，以及按需使用的 BibTeX / Biber。Windows 编译流程使用宋体、黑体、楷体、仿宋等字体。
3. PATH 中可执行的 uv，用于运行 PDF 降级。程序通过隔离环境启动 **pdf2zh-next 2.9.0** 并约束 bitstring<5.0.0；首次运行可能需要下载依赖和模型资源。
4. 可用的翻译服务地址、模型和凭证。

~~~bash
git clone https://github.com/Eric10Z4/academic-paper-translate.git
cd academic-paper-translate

# python 必须是准备给本技能使用的解释器。
python -m pip install -r requirements.txt
python -m pip install uv
python -B scripts/zotero_translate.py --doctor
~~~

--doctor 只检查基础依赖和可执行程序是否可见，不测试 API 凭证、所有宏包字体或完整 PDF 降级。MiKTeX 自动安装宏包被关闭；缺包时根据编译日志补齐后重试。

也支持从仓库构建安装包：

~~~bash
python -m pip install ".[pdf]"
paper-translate --help
paper-translate --config "/absolute/path/to/config.json" --input "2201.02609" --output-dir "./output/2201.02609"
~~~

安装包包含提示词和版本资源，版本统一来自 VERSION；pdf 扩展安装 uv，实际降级引擎仍按脚本固定版本隔离运行。安装包用户通过 --config 或 ACADEMIC_TRANSLATE_CONFIG 指定包目录以外的私有 JSON，不向 site-packages 写入凭证。

## 配置翻译服务

默认后端为 cpa。复制 JSON 模板，再在本机编辑凭证：

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

将占位内容换成服务实际支持的配置。config.example.json 中的模型名是已有部署示例，不代表每个服务均支持它。不要提交私有配置、凭证或含凭证的备份。

- CLI 支持 --provider cpa、deepseek、ollama；切换时在 providers 下增加同名配置，或设置对应环境变量。
- CPA_API_KEY / CPA_BASE_URL / CPA_MODEL 等环境变量优先于 JSON；其他后端使用 DEEPSEEK_ 或 OLLAMA_ 前缀。
- 默认读取技能根目录的 config.local.json；也可用 --config /path/to/config.json 或 ACADEMIC_TRANSLATE_CONFIG 指定。
- 当前程序**不读取旧 config.yaml；无效的 config.example.yaml 已移除**，也没有 --provider openai 选项。其他支持当前 Chat Completions 请求格式的兼容端点，可通过 cpa 的地址、密钥和模型配置使用。
- --workers、--prompt 等参数从 CLI 传入；旧 YAML 中的 translation 字段不生效。

## 使用示例

以下命令从仓库根目录运行；在 Hermes 中应替换为下一节指定的解释器和脚本绝对路径。

~~~bash
# arXiv 编号；完整 arXiv URL 或准确英文标题也可作为 --input。
python -B scripts/zotero_translate.py \
  --input "2201.02609" --output-dir "./output/2201.02609"

# 本地 TeX 工程；多入口工程可显式指定主文件。
python -B scripts/zotero_translate.py \
  --input "./paper_source" --main "main.tex" \
  --original "./paper.pdf" --output-dir "./output/paper" --workers 4

# 已下载 original.pdf 的论文目录：保留原文并原地增加译文。
python -B scripts/zotero_translate.py \
  --input "./papers/example/original.pdf" --output-dir "./papers/example"
~~~

原地归档要求已有 original.pdf 与明确传入的原文 SHA-256 一致，程序保留其内容和时间戳。不同论文、不同原文或未登记的旧译文会被拒绝；已有普通笔记不影响接纳。输出目录不能是原 TeX 工程根目录。

| 参数 | 用途 |
| --- | --- |
| --original PDF | 指定原文。仅有 TeX 时可省略，程序尝试编译未翻译源码作为对照，并记录来源 |
| --no-fallback | 原生流程失败就停止，不转 PDF 降级 |
| --workers 1..16 | 并发数量，默认 4 |
| --compile-timeout 180 | 单次编译子进程时限，单位秒，不是整个流程总时限 |
| --prompt cs_ai_specialized | 原生正文提示词；另有 zotero_default、math_formula_preservation。PDF 降级使用独立提示词 |
| --help | 查看完整参数 |

--arxiv、--dir、--pdf 仍可作为输入别名，但一次只能选一个输入参数。旧 --output-zip 已删除，统一使用 --output-dir。

## 在 Hermes 中调用

将技能放到**实际安装配置使用的 Hermes skills 目录**。本次验收的 Windows 安装位于 %LOCALAPPDATA%/hermes/skills/academic-paper-translate；其他安装应确认自己的目录。

本机 Hermes terminal 使用 Bash。以下示例直接调用已有翻译依赖环境，不启动 PowerShell：

~~~bash
PYTHON="$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"
SKILL_DIR="$LOCALAPPDATA/hermes/skills/academic-paper-translate"
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" --doctor
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" \
  --input "C:/papers/example/original.pdf" --output-dir "C:/papers/example"
~~~

按实际安装修改路径；翻译环境与 Hermes 自身启动解释器可以不同。旧 scripts/run.ps1 仅保留兼容用途。

在 Hermes 对话中可说：“使用 academic-paper-translate 翻译这篇论文，并检查结果清单。”长任务按 [SKILL.md](SKILL.md) 用后台执行并等待结束。上次进程异常结束时，先确认锁文件记录的进程已退出，再清理 .translation/active.lock 重试。

## 输出与验收状态

以输出目录的 **translation_manifest.json** 为准，不以目录中是否存在某个 PDF 判断成功。

| 状态 | 交付物与含义 |
| --- | --- |
| complete_native | original.pdf、chinese_mono.pdf、bilingual_dual.pdf、chinese_source.zip；通过原生流程检查及 ZIP 解压重编译 |
| complete_fallback | 三份标准 PDF；若产生未完成源码包，另附 chinese_source_uncompiled.zip。必须说明采用 PDF 降级 |
| review_required | 文件已生成，但有排版或字体警告，需要检查；CLI 返回非零 |
| failed | 本次失败；查看清单中的阶段和日志，不把旧产物当作本次成功结果 |

.translation/ 保存工作副本和缓存。每篇论文使用独立输出目录；分享前检查日志及清单中的本机路径和论文内容。未编译源码包可能仍是原文或只完成部分处理，不代表完整中文源码。

## 已验证范围与限制

- **v2.1：86 项确定性回归通过；7 个 Hermes 端到端场景完成预期结果**，覆盖原生编译、PDF 降级、安全宏、预存原文、缓存续跑等。另通过 Hermes 验证了直接 CLI 入口。详见 [v2.1 报告](docs/v2.1.0-修复与Hermes复验报告.md)。
- v2.0 还检查过 CVPR、NeurIPS、ICML、ACM 样式构造样本及多页排版。它们不是完整真实论文语料的逐句人工验收；历史 62 篇论文没有全量重跑。详见 [修复验收报告](docs/学术论文翻译Skill修复与验收报告.md)。
- 中文重排可能改变换行、字体、浮动位置和页数。左右按页码配对不代表语义逐段对齐；不承诺“100% 原版式不变”。
- 自定义宏仅按受支持规则检查；长文本藏在冻结宏中不会被翻译。任意 .sty/.cls、动态 TeX 或未知结构不保证支持。
- PDF 降级关闭表格文字翻译并启用图表保护，但依赖版面识别，不能提供 TeX 源码级冻结保证。
- 双语合成尝试迁移普通网页链接、文档内跳转和目录，不保证所有 PDF 注释、动作和书签属性完整保留。
- 源码 ZIP 在当前环境重编译通过，不代表在所有电脑或 Overleaf 上开箱即用；TeX 发行版、宏包和系统字体未打包。
- 自动检查无法证明每句译文准确、无遗漏或整篇术语完全一致。正式引用或研究使用前仍需核对关键内容。

## 测试与仓库内容

~~~bash
# 确定性测试，不需要真实翻译 API。
python -B -m unittest discover -s tests -p 'test_*.py' -v

# 在 Hermes 中运行；需要配置好的 CPA、编译环境和 uv，会实际调用翻译服务。
python -B tests/run_acceptance.py --workspace "/absolute/path/to/new-acceptance-workspace"
~~~

真实验收使用新的独立目录，并遵循 [AUDIT_SPEC.md](AUDIT_SPEC.md)。以上翻译测试数字指已记录的 v2.1 验收，不是持续集成状态徽章。v2.1.1 另外检查构建、安装后资源与命令行入口；CI 不调用真实翻译服务。

主要代码位于 scripts/（流程、语法保护、编译、PDF 降级）与 adapters/；提示词在 prompts/，测试在 tests/，历史报告在 docs/。companion-skills/ 中的下载技能可按需单独下载原文和源码；需要翻译时直接使用主入口。

## 致谢与许可证

提示词参考 [Zotero PDF Translate](https://github.com/windingwind/zotero-pdf-translate)；PDF 降级使用 [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next)。本项目不是这些项目的官方发行版。

凭证与历史清理说明见 [SECURITY.md](SECURITY.md)。采用 [MIT License](LICENSE)。
