---
name: academic-paper-translate
description: Translate English academic papers into Simplified Chinese, preferring original LaTeX sources and checked local PDF compilation. Use for arXiv IDs, paper titles, local PDFs, and TeX projects; preserve tables, formulas and references and deliver verified PDFs and source archives.
---

# 学术论文原格式翻译

使用本技能完成全文翻译，不输出论文摘要、导读、核心创新点或自行增加的评述。表格正文、方法名、数值、公式、引用键和代码必须由程序保护；表格内仅翻译 caption。不要绕过校验手动把整份 TeX 交给模型。

## Hermes 执行入口

以下是已验收 Windows 安装的 Bash 示例；按实际安装位置设置解释器与技能目录。Hermes terminal 的 Shell 应以当前安装为准。直接调用已安装翻译依赖的指定 Python，不启动 PowerShell，不把 PowerShell 的 `&` 或 `$env:...` 写入 Bash 命令：

```bash
PYTHON="$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"
SKILL_DIR="$LOCALAPPDATA/hermes/skills/academic-paper-translate"
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" --doctor
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" --input "论文标题、arXiv编号、PDF绝对路径或TeX目录" --output-dir "论文归档目录" --workers 4
```

上例中的 Python 是本技能的依赖环境，不要求它与 Hermes 自身启动解释器相同。依赖缺失时，用同一个解释器安装根目录 `requirements.txt`；不要悄悄改用系统 Python。旧 `run.ps1` 仅为已有 PowerShell 调用保留，Hermes 不使用它。其他安装位置替换为对应的绝对路径；其他系统可直接用已安装依赖的 Python 执行 `scripts/zotero_translate.py`。

完整论文可能超过 Hermes 终端默认前台时限。请用终端工具的 `background=true, notify=true` 启动，再用 process 工具等待结束并读取日志；不要反复重启同一个输出目录，也不要让前台超时杀掉编译或翻译进程。若上次进程被外部终止，先核对 `.translation/active.lock` 中的 PID；仅确认该进程已经退出后，才清理这份锁文件重试，保留原有日志与缓存。

默认后端为现有 CPA 和 `gemini-3.8-flash-high`。凭证从 `config.local.json` 或 `CPA_API_KEY` 读取；不要在回复、日志、命令参数或分享的 ZIP 中展示。环境变量优先于本地配置。其他后端通过 `--provider deepseek` 或 `--provider ollama` 选择。

## 输入与执行

- 优先从用户给定 TeX 工程或 arXiv 获取源码。标题仅在高置信匹配时采用；无法确定时说明需要论文编号或原 PDF，不把其他论文冒充目标论文。
- 本地 PDF 路径优先按文件识别，即使文件名包含 arXiv 编号。若无可用源码，自动采用 PDF 降级流程。
- 原工程只读，翻译和编译均在输出目录的 `.translation` 工作副本中进行。不要把输出目录设置成原工程根目录。
- 已经下载 `论文目录/original.pdf` 时，将这个文件作为 `--input`，将其父目录作为 `--output-dir`，即可原地归档。程序确认预存原文与输入的 SHA-256 一致后接纳，并保留原文件；TeX 工程配有原文或明确传入 `--original` 时同样适用。仅有标题或编号不能证明已有 PDF 属于该论文，需明确指定原文。未登记的旧译文、不同论文记录或不同内容的原文仍会拒绝；同一输入的已登记目录可以续跑，其他笔记文件不受影响。
- 多主文件工程用 `--main 相对路径`。如有官方英文 PDF，使用 `--original 绝对路径`。仅有源码时会编译原英文工程作为对照，并在记录中标注来源，不能称其为另行取得的官方 PDF。
- 模型请求只包含可编辑自然语言和不透明占位符；表格数据、公式、数值和原始引用键不会被发送。占位符有缺失、重复、变化或顺序破坏时重试，仍失败则停止原生分支并留档。
- 自定义无参宏按实际定义检查：支持 `newcommand` 等声明、无参数的 `def/gdef`、简单 `let` 别名，以及纯文字、常见文字字体包装、`xspace`、嵌套安全宏和受限的 `ensuremath` 表达式。安全宏本身完整冻结，不交给模型翻译；名称不构成白名单，重新定义过的常见命令也会检查。参数宏、条件展开、递归、隐藏环境/输入/赋值等未经支持的结构继续明确拒绝。只分析已遍历源文件中的定义，不承诺理解任意 `.sty/.cls` 或动态 TeX；需要翻译的长文本不要藏在缩写宏里。
- 遇到动态输入路径、无法证明安全的宏、未知环境、环境不平衡、非 UTF-8 源码等，程序保留原因并尝试降级。不要通过删除校验或凭名称加白名单提高原生成功率。
- 默认采用 Zotero 学术提示词。`--prompt cs_ai_specialized` 或 `--prompt math_formula_preservation` 可选择专门提示词；不要自加解读要求。

## 检查与交付

命令结束后必须读取输出目录中的 `translation_manifest.json`，根据其状态报告结果：

| 状态 | 应如何交付 |
| --- | --- |
| `complete_native` | 交付 original.pdf、chinese_mono.pdf、bilingual_dual.pdf、chinese_source.zip；说明清单中实有的页数变化或来源说明 |
| `complete_fallback` | 交付三 PDF；有源码时另附 chinese_source_uncompiled.zip；明确说明采用 PDF 降级，冻结区的 TeX 级保证不适用 |
| `review_required` | 文件已产生，但存在排版警告；说明需检查的位置，不宣称全部验收通过 |
| `failed` | 报告失败阶段与日志路径；保留源码和缓存，不把之前留下的 PDF 当成本次成功产物 |

原生完成必须通过正文片段完整性校验、干净目录编译、引用收敛、PDF 可读性检查、双语页数检查和源码 ZIP 解压重编译。英文和中文页数不同会保留全部页，缺失侧注明；按页码并排不等同于语义段落完全对齐。翻译后的文字长度会改变换行、浮动位置或分页，不承诺与英文逐像素一致。

PDF 降级固定使用 pdf2zh-next 2.9.0，关闭表格文字翻译并启用图表保护；OCR 布局识别无法提供源码字节级证明。原文本就没有 TeX 时，不伪造源码 ZIP。

部分旧模板的 Times/Helvetica/Courier 字体声明与 XeLaTeX 的 TU 编码不兼容。只有日志实际报告相关字体族缺失时，编译器才在工作副本中改用对应的 Unicode 字体（Windows 上为 Times New Roman、Arial、Courier New），记录兼容重试并把设置留在可重编译源码包中。它不保证字体与发行版逐字形一致；残留字体替换警告与 Overfull 警告都标为 `review_required`。宏包缺失时查阅编译日志，用 MiKTeX 安装明确缺失的依赖后再重试；不要忽略报错或换一个旧 PDF。

不更新论文集“创新点”导读，也不重新翻译原工程。可以复用 `.translation/cache.json` 中已验证片段；不同论文必须使用不同输出目录。

## 维护与测试

修改后用 Hermes 的 Python 运行 `-B -m unittest discover -s 技能绝对路径/tests -p 'test_*.py' -v`，包含原有回归和兼容性回归。真实翻译验收通过 Hermes 加载本技能并执行 `tests/run_acceptance.py --workspace 独立测试目录`；该测试实际调用现有 CPA，覆盖多文件表格、公式、引用、仅有 bbl、纯 PDF 降级、编译失败降级、安全宏原生编译、预存原文归档和同输入缓存续跑。测试前读 [AUDIT_SPEC.md](AUDIT_SPEC.md)，验收日志不能用模型口头声明替代。

## 论文身份与数值完整性

本地 PDF 中的 arXiv 链接、文件名编号和标题搜索结果仅是源码候选。程序下载候选官方 PDF，要求文件相同或每页完整提取文字一致且总文字量充分，才采用其源码。无法确认、版本或排版不同、扫描件等采用原 PDF 降级，并在清单记录原因。正文带正负号的小数、前导小数点以及科学计数法作为完整冻结原子保护；公式继续整体冻结。
