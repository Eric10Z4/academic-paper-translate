# Academic Paper Translate：面向科研阅读的论文全文翻译工作流

[English](README_EN.md) · [Hermes 技能说明](SKILL.md) · [核验规范](AUDIT_SPEC.md)

面向 Hermes 的英文学术论文全文翻译技能。当前代码版本为 **2.2.0**：优先翻译 LaTeX 源码并在本地编译中文 PDF；原生流程不可用时尝试 PDF 翻译，并强制进入待视觉核验状态；核验通过后执行收尾，默认不保留生成的源码包。

支持 arXiv 编号或链接、英文论文标题、本地 PDF 和 TeX 工程目录。翻译目标为简体中文，要求模型只输出译文，不生成摘要或论文导读。

## 项目目标与工程重点

面向英文论文阅读，把原文获取、正文翻译、结构保护、LaTeX 编译与双语 PDF 交付组织成可追踪的工作流。重点处理论文翻译中的公式与数值完整性、原文来源确认、失败降级和重复运行问题。

| 工程方向 | 解决的问题 | 代码入口 |
| --- | --- | --- |
| 来源与任务编排 | 核对本地 PDF 与候选论文，组织原生翻译 / PDF 降级和结果清单 | [zotero_translate.py](scripts/zotero_translate.py) |
| LaTeX 结构保护 | 区分可翻译文本与受保护内容，保留公式、引用键和完整数值 | [latex_syntax.py](scripts/latex_syntax.py) |
| 模型适配 | 通过配置切换 CPA、DeepSeek、Ollama 等后端 | [adapters](adapters/) |
| 可验证交付 | 回归检查、源码包重编译、安装后入口验证 | [tests](tests/)、[核验规范](AUDIT_SPEC.md) |

**技术栈：** Python · PyMuPDF · LaTeX / XeLaTeX · LLM API · Hermes Skill · pdf2zh-next

## 工作方式

- **来源核对**：本地 PDF 中的 arXiv 编号、引用或文件名仅作为候选；通过官方 PDF 的文件一致性或完整分页文本核对后才使用对应源码，未确认时保留传入的 PDF 进入降级流程。
- **源码优先**：在工作副本中提取受支持的正文、标题和 caption，冻结公式、表格正文、数值（含负号、小数和科学计数法）、引用键和代码，检查占位符是否完整恢复。
- **本地编译与核验**：采用 XeLaTeX，按需调用 BibTeX 或 Biber，检查引用及编译收敛；源码 ZIP 还会解压到新目录重新编译。
- **明确降级**：找不到可用源码，或原生解析、翻译校验、编译失败时，尝试固定版本的 pdf2zh-next。没有有效原 PDF 时仍可能失败。
- **双语 PDF**：原文在左、中文在右，按页码配对；页数不同时保留全部页面，并在缺页侧标注说明。
- **核验后收尾**：Hermes 查看全部中文页面并放大对照公式、分数和算法；核验记录绑定当前三 PDF 散列。通过后删除本次工作副本和已登记源码包，保留 PDF、清单、诊断记录及译文缓存。原工程不被修改。

解析器不是完整的 TeX AST 或宏展开器。它只支持部分已知结构；未知或无法证明安全的结构会导致原生分支失败或降级。源码保护也不等于所有真实论文的语义和排版均已获得保证。

## 环境与安装

已完成的端到端验收基于 **Windows、Hermes、Python 3.13、MiKTeX XeLaTeX 和本地 CPA**。其他平台、Python 版本及模型后端尚未完成同等范围的真实翻译验收。

准备以下组件：

1. 专用 Python 环境，安装 [requirements.txt](requirements.txt) 中的 PyMuPDF。
2. XeLaTeX、论文需要的宏包和字体，以及按需使用的 BibTeX / Biber。Windows 编译流程使用宋体、黑体、楷体、仿宋等字体。
3. PATH 中可执行的 uv，用于运行 PDF 降级。程序通过隔离环境启动 **pdf2zh-next 2.9.0 / BabelDOC 0.6.2** 并约束 bitstring<5.0.0；首次运行可能需要下载依赖和模型资源。
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
| --finalize DIR --visual-review JSON | 根据真实视觉核验记录执行收尾；与输入参数互斥 |
| --keep-source | 收尾时保留已登记的源码 ZIP，默认移除 |
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
| complete_native | 原生程序检查及 ZIP 重编译通过；仍须检查 visual_review 与 cleanup，完成视觉检查和收尾后交付三 PDF |
| complete_fallback | PDF 降级产物已经通过绑定当前 PDF 的视觉核验并完成收尾；交付三 PDF，说明源码级保证不适用 |
| review_required | 所有 PDF 降级，以及有排版/字体警告的原生结果；文件已生成但未完成验收，CLI 返回非零 |
| failed | 本次失败；查看清单中的阶段和日志，不把旧产物当作本次成功结果 |

先渲染查看全部中文页，并按内容对照英文中的公式和算法。根据 [视觉核验格式](references/visual_review.md) 记录实际观察，随后运行：

~~~bash
python -B scripts/zotero_translate.py --finalize "./output/paper" --visual-review "./review.json"
~~~

成功交付要求 `visual_review.status=passed` 且 `cleanup.status=complete`。默认移除本次运行目录及散列匹配的已登记源码 ZIP；用户需要源码时加 `--keep-source`。失败或未检查时保留诊断现场，不删除原始输入、笔记或未知文件。旧失败运行不做无差别清理。每篇论文使用独立输出目录。

## 已验证范围与限制

- **v2.2：本机 152 项回归，149 项通过、3 项因 Windows 链接权限跳过。** Hermes 真实完成行内分数小样例与 SCORE 全文原生复验；SCORE 246 个片段校验通过、三份 PDF 均为 13 页、源码 ZIP 重编译及逐页视觉核验通过。小样例和 SCORE 均完成收尾。详见 [v2.2 记录](docs/v2.2.0-formula-validation.md)。

- v2.1.1 后续修复记录为 92 项确定性回归通过，覆盖来源误匹配和完整数值保护；这些检查继续保留在当前测试集中。
- **v2.1：86 项确定性回归通过；7 个 Hermes 端到端场景完成预期结果**，覆盖原生编译、PDF 降级、安全宏、预存原文、缓存续跑等。另通过 Hermes 验证了直接 CLI 入口。详见 [v2.1 报告](docs/v2.1.0-修复与Hermes复验报告.md)。
- v2.0 还检查过 CVPR、NeurIPS、ICML、ACM 样式构造样本及多页排版。它们不是完整真实论文语料的逐句人工验收；历史 62 篇论文没有全量重跑。详见 [修复验收报告](docs/学术论文翻译Skill修复与验收报告.md)。
- 中文重排可能改变换行、字体、浮动位置和页数。左右按页码配对不代表语义逐段对齐；不承诺“100% 原版式不变”。
- 自定义宏仅按受支持规则检查；长文本藏在冻结宏中不会被翻译。任意 .sty/.cls、动态 TeX 或未知结构不保证支持。
- **纯 PDF 公式错排尚未通用解决。** 真实 PDF-only 样例仍出现分数拆散与算法合并，必须保留待核验状态。保留线条和风险页提示不能证明公式完整，也不能代替查看全部页面。
- 正常 `looseness` 整数赋值、受支持的重音与会议模板命令不再误拒；未知动态语法仍保守处理。算法主体按原文冻结，只翻译标题。网络错误、下载到无法识别的响应和主文件歧义均不等于论文没有源码。
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

真实验收使用新的独立目录，并遵循 [AUDIT_SPEC.md](AUDIT_SPEC.md)。以上真实翻译数字对应各版本的已记录验收；v2.2 的程序测试通过不代表 PDF-only 排版通过。CI 运行确定性回归、构建和安装后入口检查，不调用真实翻译服务。

主要代码位于 scripts/（流程、语法保护、编译、PDF 降级）与 adapters/；提示词在 prompts/，测试在 tests/，历史报告在 docs/。companion-skills/ 中的下载技能可按需单独下载原文和源码；需要翻译时直接使用主入口。

## 致谢与许可证

提示词参考 [Zotero PDF Translate](https://github.com/windingwind/zotero-pdf-translate)；PDF 降级使用 [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next)。本项目不是这些项目的官方发行版。

凭证与历史清理说明见 [SECURITY.md](SECURITY.md)。采用 [MIT License](LICENSE)。
