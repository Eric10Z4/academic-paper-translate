---
name: arxiv-paper-downloader
description: Use when downloading arXiv papers and LaTeX sources.
---

# arXiv Paper Downloader & Adapter Skill

专门用于快速解析、下载 arXiv 论文（PDF + LaTeX 完整源码包），并作为适配器与 `academic-paper-translate` 配合使用。

## 适用场景
1. 用户提供 arXiv 编号（例如 `2201.02609`、`2211.11727`）或完整 URL（`https://arxiv.org/abs/...`）。
2. 需要获取官方原始 PDF 或 `.tar.gz` 矢量级 LaTeX 源码工程。

## 执行命令

### 1. 下载原始 PDF
```bash
curl -sL "https://arxiv.org/pdf/<arxiv_id>.pdf" -o "<保存路径>/<arxiv_id>.pdf"
```

### 2. 下载并解压 LaTeX 源码包
```bash
mkdir -p "<目标目录>" && \
curl -sL "https://arxiv.org/e-print/<arxiv_id>" -o "<目标目录>/source.tar.gz" && \
tar --force-local -xzf "<目标目录>/source.tar.gz" -C "<目标目录>" && \
rm "<目标目录>/source.tar.gz"
```

### 3. 一键联动翻译
下载完成后，可直接调用 `academic-paper-translate`：
```bash
python scripts/zotero_translate.py \
  --dir "<目标目录>" \
  --output-zip "<保存路径>/<arxiv_id>_zh.zip"
```
