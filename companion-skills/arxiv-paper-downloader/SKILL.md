---
name: arxiv-paper-downloader
description: Download arXiv original PDFs and available LaTeX sources, or pass a paper to academic-paper-translate when translation is requested.
---

# arXiv 下载与翻译联动

使用用户给定的 arXiv 编号或链接。需要全文翻译时使用主技能入口；只有下载请求时才执行下载步骤，不额外调用翻译 API。

## 解释器与路径

在 Hermes 中使用实际安装了翻译依赖的 Python 和主技能目录。以下为 Windows Bash 示例；安装位置不同则调整，其他系统也可指向对应解释器：

~~~bash
PYTHON="$LOCALAPPDATA/hermes/hermes-agent/venv/Scripts/python.exe"
SKILL_DIR="$LOCALAPPDATA/hermes/skills/academic-paper-translate"
~~~

## 用户要求翻译

主技能自行获取原文和源码，不必先运行另一套下载及解压命令：

~~~bash
PYTHONIOENCODING=utf-8 "$PYTHON" -B "$SKILL_DIR/scripts/zotero_translate.py" --input "2201.02609" --output-dir "C:/papers/2201.02609"
~~~

已有源码时将 --input 改为源码目录；已有官方 PDF 可通过 --original 指定。输出不能覆盖原 TeX 工程根目录。使用 --output-dir；旧 --output-zip 已删除。

长任务按主技能 SKILL.md 在 Hermes 后台执行，并读取 translation_manifest.json 判断结果和是否降级。

## 用户只要求下载

从主技能目录运行，使用新的输出文件或独立空目录。已有目标时停止，避免覆盖：

~~~bash
cd "$SKILL_DIR"

# 下载并检查原 PDF；参数依次为 arXiv 编号和目标文件。
PYTHONIOENCODING=utf-8 "$PYTHON" -B -c "import sys; from pathlib import Path; from scripts.zotero_translate import download_arxiv_pdf; p=Path(sys.argv[2]); sys.exit('Target already exists') if p.exists() else None; sys.exit(0 if download_arxiv_pdf(sys.argv[1],p) else 2)" "2201.02609" "C:/papers/2201.02609/original.pdf"

# 获取可用源码，使用主技能的受限解压逻辑；目标目录必须不存在。
PYTHONIOENCODING=utf-8 "$PYTHON" -B -c "import sys; from pathlib import Path; from scripts.zotero_translate import fetch_arxiv_source; p=Path(sys.argv[2]); sys.exit('Target already exists') if p.exists() else None; sys.exit(0 if fetch_arxiv_source(sys.argv[1],p) else 2)" "2201.02609" "C:/papers/2201.02609/source"
~~~

下载命令成功才报告成功；未提供或无法识别源码时如实说明，不把 PDF 伪装成源码包。下载失败时保留诊断，不自动删改已有论文文件。
