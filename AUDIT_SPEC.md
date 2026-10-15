# 学术论文翻译技能验收规范

本文件是修复版的可执行验收标准。用户桌面原始规范保持不变，修改前技能另有原版备份。本技能应满足源内容保护、完整翻译、真实编译、完整交付和可追踪降级；不把“发现 PDF 文件”视为编译成功。

## 确定性回归

通过 Hermes 加载本技能，按 SKILL.md 的 Bash 入口调用指定 Python，执行 `-B -m unittest discover -s 技能绝对路径/tests -p 'test_*.py' -v`。同时运行 `test_regression.py` 与 `test_compatibility.py`；这些测试不调用真实模型，采用受控故障，要求全部通过。覆盖：

- 表格各环境、空行、嵌套、input 子文件以及跨文件环境状态。
- 行内和展示数学、代码、引用可选参数、占位符缺失、重复和重排。
- 正文不因注释、相邻公式、缺少空行而跳过；未知宏不得静默漏译。
- 新生成的 TeX 特殊字符安全处理，原数字和引用原子还原。
- 旧 PDF 不得覆盖失败状态，bbl 不丢失，xeCJK 管理区块实际切换。
- 双语页数采用较大值，不截断尾页，并保留支持的页面链接。
- 论文标题、本地编号 PDF、不同后端、异常降级、失败退出码、只读输入、归档解压路径边界。
- 格式化缩写、嵌套安全宏、无参声明、别名、受限 ensuremath、后随独立文字组；危险同名定义、晚重定义、作用域替代、递归和参数宏在模型调用前被拒绝。
- 同目录预存原文的接纳与续跑，内容不匹配、未登记译文、输入与 --original 冲突、运行中原文被修改等情形不得覆盖原文件。

## 真实翻译验收

仅通过 Hermes 启动 `tests/run_acceptance.py --workspace 独立目录`。它会使用当前配置的 CPA 模型进行真实翻译，不使用固定假译文。默认七个场景为：

1. 多文件双栏工程：caption 可选参数、数学表达式、跨文件表格、正文百分号、BibTeX 和引用。要求 `complete_native`，冻结行文件、公式和引用键保持一致。
2. 仅有 bbl 的工程：无 bib 文件仍能编译，交付 ZIP 保留 bbl 并能独立重编译。
3. 无公开源码的本地 PDF：程序阶段必须为 `review_required`，标准三 PDF 齐全，页面数不丢失；真实查看页面后才能 finalize 为 `complete_fallback`。
4. 无法编译的源码加原 PDF：要求自动进入待视觉核验的降级并暂存未编译源码 ZIP；验收后默认删除本次源码和包。
5. 格式化缩写、嵌套宏、def、let 和 ensuremath 的双栏工程：目标目录预存匹配 original.pdf，要求 complete_native，宏定义文件与表格行字节不变，交付源码包重编译成功。
6. 同一宏工程续跑：复用此前真实翻译且重新通过完整性检查的缓存，仍要求原生编译成功。
7. 以归档目录内 original.pdf 为输入、其父目录为输出：完成真实 PDF 降级，原文件内容与修改时间均保持不变。

每个场景必须检查输入文件散列不变、manifest 实际状态、PDF 可读性、页数和源码包内容。编译、合成和源码 ZIP 重编译记录均位于本次 `.translation/runs` 目录。渲染并查看中文 PDF 的全部页面，对公式、分数、算法和表格放大核对，并检查尾页完整；自动测试不能取代视觉和语义检查。

## 额外验收与已知边界

真实会议模板及公开论文应逐步回归，记录模板、版本、论文 ID、模式和失败原因。未运行的模板或论文不能填写通过。LaTeX 的动态宏、动态文件名及所有自定义语法没有通用静态保证；遇到不支持结构时必须失败或标注降级。

中英文页码相同不证明语义逐段对齐；页数不同必须保留两边全部页并警示。`scheme=plain` 不证明换行和浮动位置与英文逐像素一致。任何 Overfull 警告使交付状态变为 `review_required`，需查看页面后处理。

PDF 降级采用视觉版面识别，不能宣称表格和公式具有 TeX 源码字节级保证。无源码时只交付三 PDF 与处理清单，不生成虚假源码包。

## 依赖和上游参考

主流程依赖锁定见 requirements.txt。PDF 降级封装固定使用 pdf2zh-next 2.9.0 / BabelDOC 0.6.2；参数按该版本的配置模型核对：

- https://github.com/PDFMathTranslate-next/PDFMathTranslate-next/tree/v2.9.0/pdf2zh_next/config
- 环境变量使用 `PDF2ZH_` 前缀；图表保护开启，`PDF2ZH_TRANSLATE_TABLE_TEXT=false`；API 凭证仅通过环境变量传递。

升级任一核心依赖后重跑上述用例，禁止只更新版本号而沿用旧验收结论。

## 分数、算法与收尾回归

用 Hermes 启动 `tests/run_formula_acceptance.py --workspace 隔离目录 --case inline_native`，验证嵌套分数、偏导数、ensuremath、算法标题与算法主体；真实 SCORE 场景使用 `--case score --source-project /path/to/score-source --original /path/to/score.pdf`，输入须为相匹配的 SCORE（arXiv:2203.04413）原始源码与英文 PDF；仓库不附论文文件，也不写死本机路径。`--case pdf_only` 用相同公式样例验证降级和待检查状态，程序返回测试通过不表示其排版通过。所有产物仍须实际渲染查看。

`test_native_formula.py` 覆盖分数原子和算法结构；`test_source_acquisition.py` 区分网络失败、PDF响应和入口歧义；`test_delivery.py` 覆盖绑定散列、页码、活动锁、输入保护、路径边界、链接和清理后的日志保留。失败/未检查的产物不得清理，检查通过后默认只交付三PDF及核验记录，源码归档可按用户要求保留。
