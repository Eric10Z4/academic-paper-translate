# 视觉核验记录与收尾

先渲染并实际查看全部中文页面。总体布局可查看清晰的缩略图；分数、公式与算法须放大对照原文。`passed` 是观察结论，不能由检查脚本直接猜测。

核验 JSON 如下，散列从当前 manifest 的 artifacts 中读取并核对实际文件。页码使用中文 PDF 的全部 1 起始页码，按顺序列出；示例只表示一页文件：

```json
{
  "reviewer": "Hermes",
  "notes": "填写实际观察：检查了哪些分数、公式和算法，警告是否影响阅读；不存在的类型写不适用。",
  "artifacts": {
    "original.pdf": "当前原文的SHA256",
    "chinese_mono.pdf": "当前中文PDF的SHA256",
    "bilingual_dual.pdf": "当前双语PDF的SHA256"
  },
  "reviewed_pages": [1],
  "checks": {
    "inline_fractions": "passed",
    "display_math": "passed",
    "algorithm_structure": "passed",
    "clipping": "passed"
  }
}
```

还可附加 `rendered_evidence`（观察过的图像路径）。没有真实观察或出现缺陷时不能将检查项写为 passed。

用翻译时同一 Python、同一脚本调用：

```bash
"<翻译环境的python>" -B "<技能目录>/scripts/zotero_translate.py" --finalize "<论文输出目录>" --visual-review "<核验记录.json>"
```

收尾核对 PDF 散列、全部页码、运行状态与目录边界；拒绝活动锁、外部目录、符号链接、改过的源码包或缺失的记录。不会删原始输入、笔记或未知 ZIP。源码包默认移除，仅用户明确需要时加 `--keep-source`。

成功后读取 manifest：`visual_review.status=passed`、`cleanup.status=complete` 才表示收尾完成。`complete_fallback` 只表示该次成品经视觉检查通过，不能推广为 PDF 翻译对任意论文都保证公式无损。
