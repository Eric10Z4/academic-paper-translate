import os
import sys
import re
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import tarfile
import argparse
from concurrent.futures import ThreadPoolExecutor

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from adapters.deepseek_adapter import DeepSeekAdapter
    from adapters.openai_adapter import OpenAIAdapter
    from adapters.ollama_adapter import OllamaAdapter
    from adapters.cpa_adapter import CPAAdapter
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adapters.deepseek_adapter import DeepSeekAdapter
    from adapters.openai_adapter import OpenAIAdapter
    from adapters.ollama_adapter import OllamaAdapter
    from adapters.cpa_adapter import CPAAdapter

DEFAULT_PROMPT_TEMPLATE = """As an academic expert with specialized knowledge in various fields, please provide a proficient and precise translation from English to Simplified Chinese of the academic text enclosed in 🔤. It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. Keep all LaTeX markup, math notation ($...$, equations), citations (\\cite{...}), references (\\ref{...}), and environment tags intact. Translate only the natural language text. The text is as follows:

🔤 __SOURCE_TEXT__ 🔤

Please provide the translated result without any additional explanation and remove 🔤."""

def load_config(config_path="config.yaml"):
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[config] Notice: could not load config file {config_path}: {e}")
    return {}

def get_adapter(provider="deepseek", config=None, api_key=None, base_url=None, model=None):
    if config and "providers" in config and provider in config["providers"]:
        cfg = config["providers"][provider]
        b_url = base_url or cfg.get("base_url")
        key = api_key or cfg.get("api_key")
        mod = model or cfg.get("model")
        if provider == "deepseek":
            return DeepSeekAdapter(base_url=b_url, api_key=key, model=mod)
        elif provider == "openai":
            return OpenAIAdapter(base_url=b_url, api_key=key, model=mod)
        elif provider == "ollama":
            return OllamaAdapter(base_url=b_url, api_key=key, model=mod)
        elif provider == "cpa":
            return CPAAdapter(base_url=b_url, api_key=key, model=mod)

    # Defaults from CLI args or environment variables
    if provider == "deepseek":
        b_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        mod = model or "deepseek-chat"
        return DeepSeekAdapter(base_url=b_url, api_key=key, model=mod)
    elif provider == "cpa":
        b_url = base_url or os.environ.get("CPA_BASE_URL", "http://127.0.0.1:8317/v1")
        key = api_key or os.environ.get("CPA_API_KEY", "")
        mod = model or "gemini-3.8-flash-high"
        return CPAAdapter(base_url=b_url, api_key=key, model=mod)
    elif provider == "ollama":
        b_url = base_url or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434/v1")
        mod = model or "qwen2.5:14b"
        return OllamaAdapter(base_url=b_url, api_key="ollama", model=mod)
    else:  # openai
        b_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        mod = model or "gpt-4o-mini"
        return OpenAIAdapter(base_url=b_url, api_key=key, model=mod)

# ----------------------------------------------------------------------
# 1. 自动寻找 arXiv 编号与下载 LaTeX 源码包
# ----------------------------------------------------------------------

def find_arxiv_id_from_pdf(pdf_path):
    """从本地 PDF 前 3 页文本中正则匹配 arXiv 编号"""
    if not fitz or not os.path.exists(pdf_path):
        return None
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for i in range(min(3, len(doc))):
            text += doc[i].get_text() + "\n"
        m = re.search(r'arxiv[:\.\s/]+([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)', text, re.IGNORECASE)
        if m:
            return m.group(1)
        m2 = re.search(r'arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)', text, re.IGNORECASE)
        if m2:
            return m2.group(1)
    except Exception as e:
        print(f"[find_arxiv_id_from_pdf] Error reading PDF: {e}")
    return None

def search_arxiv_by_title(title):
    """通过 arXiv API 根据论文标题搜索匹配的 arXiv ID"""
    if not title or len(title.strip()) < 5:
        return None
    clean_title = re.sub(r'[\r\n\t]+', ' ', title).strip()
    clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean_title)
    query_title = " ".join(clean_title.split()[:12])
    try:
        query = urllib.parse.quote(f'ti:"{query_title}"')
        url = f"http://export.arxiv.org/api/query?search_query={query}&max_results=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read().decode('utf-8')
        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        if entry is not None:
            id_elem = entry.find('atom:id', ns)
            if id_elem is not None and id_elem.text:
                m = re.search(r'([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)', id_elem.text)
                if m:
                    return m.group(1)
    except Exception as e:
        print(f"[search_arxiv_by_title] API query failed: {e}")
    return None

def fetch_arxiv_source(arxiv_id, target_dir):
    """从 arXiv 下载 e-print 源码包并解压"""
    clean_id = arxiv_id.lower().replace('arxiv:', '').strip()
    os.makedirs(target_dir, exist_ok=True)
    tar_path = os.path.join(target_dir, f"{clean_id}.tar.gz")
    url = f"https://arxiv.org/e-print/{clean_id}"
    print(f"[fetch_arxiv_source] Downloading arXiv source from {url}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(tar_path, 'wb') as out_f:
            out_f.write(resp.read())
    except Exception as e:
        print(f"[fetch_arxiv_source] Failed to download arXiv source: {e}")
        return False

    print("[fetch_arxiv_source] Extracting source package...")
    try:
        with tarfile.open(tar_path, "r:*") as tar:
            tar.extractall(path=target_dir)
        os.remove(tar_path)
    except Exception:
        try:
            import gzip
            with gzip.open(tar_path, 'rb') as gz_in:
                content = gz_in.read()
            with open(os.path.join(target_dir, "main.tex"), "wb") as f_out:
                f_out.write(content)
            os.remove(tar_path)
        except Exception as e2:
            print(f"[fetch_arxiv_source] Failed to extract source archive: {e2}")
            return False

    has_tex = False
    for root, _, files in os.walk(target_dir):
        if any(f.endswith(".tex") for f in files):
            has_tex = True
            break
    if has_tex:
        print(f"[fetch_arxiv_source] Successfully extracted LaTeX source to {target_dir}")
        return True
    else:
        print(f"[fetch_arxiv_source] No .tex files found in extracted archive.")
        return False

# ----------------------------------------------------------------------
# 2. LaTeX 宏与花括号平衡匹配提取
# ----------------------------------------------------------------------

def find_command_positions(text, cmd=r'\caption'):
    """基于花括号平衡算法，精准定位并提取类似 \\caption{...} 的参数范围"""
    results = []
    idx = 0
    while True:
        pos = text.find(cmd, idx)
        if pos == -1:
            break
        brace_pos = text.find('{', pos + len(cmd))
        if brace_pos == -1 or brace_pos > pos + len(cmd) + 10:
            idx = pos + len(cmd)
            continue
        depth = 1
        curr = brace_pos + 1
        while curr < len(text) and depth > 0:
            if text[curr] == '{':
                depth += 1
            elif text[curr] == '}':
                depth -= 1
            curr += 1
        if depth == 0:
            results.append((pos, brace_pos, curr))
            idx = curr
        else:
            idx = pos + len(cmd)
    return results

# ----------------------------------------------------------------------
# 3. 核心：表格/公式完全冻结与段落翻译
# ----------------------------------------------------------------------

TABLE_ENVS = [
    'tabular', 'tabular*', 'tabularx', 'tabulary', 'longtable', 'supertabular'
]
MATH_ENVS = [
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'multline', 'multline*', 'eqnarray', 'eqnarray*'
]
CODE_ENVS = [
    'verbatim', 'lstlisting', 'minted', 'algorithmic', 'algorithm2e'
]

def split_into_paragraphs(tex_content):
    return re.split(r'(\n\s*\n+)', tex_content)

def translate_caption_inside_block(block, adapter, prompt_template):
    """针对 table / figure 容器环境：数据与排版 100% 冻结，仅翻译 \\caption{...}"""
    positions = find_command_positions(block, r'\caption')
    if not positions:
        return block

    new_block = block
    for pos, brace_start, end_pos in reversed(positions):
        original_caption = block[brace_start + 1:end_pos - 1]
        if re.search(r'[a-zA-Z]{3,}', original_caption):
            try:
                translated_caption = adapter.translate(original_caption, prompt_template)
                new_block = new_block[:brace_start + 1] + translated_caption + new_block[end_pos - 1:]
            except Exception as e:
                print(f"[translate_caption] Error translating caption: {e}")
    return new_block

def translate_tex_file(file_path, output_path=None, adapter=None, prompt_template=None, max_workers=4):
    if output_path is None:
        output_path = file_path
    if adapter is None:
        adapter = get_adapter("deepseek")
    if prompt_template is None:
        prompt_template = DEFAULT_PROMPT_TEMPLATE

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    parts = split_into_paragraphs(content)
    tasks = []
    caption_tasks = []

    for idx, part in enumerate(parts):
        if idx % 2 == 0:
            stripped = part.strip()
            if stripped.startswith('%'):
                continue
            if "\\begin{document}" in content:
                doc_start = content.find("\\begin{document}")
                part_pos = content.find(part)
                if part_pos < doc_start and not stripped.startswith("\\title"):
                    continue

            is_table_block = any(f"\\begin{{{env}}}" in stripped for env in TABLE_ENVS) or \
                             "\\begin{table}" in stripped or "\\begin{table*}" in stripped

            is_math_block = any(f"\\begin{{{env}}}" in stripped for env in MATH_ENVS)
            is_code_block = any(f"\\begin{{{env}}}" in stripped for env in CODE_ENVS)
            is_bib_block = "\\begin{thebibliography}" in stripped

            if is_table_block or "\\begin{figure}" in stripped or "\\begin{figure*}" in stripped:
                if r'\caption' in stripped:
                    caption_tasks.append((idx, part))
                continue

            if is_math_block or is_code_block or is_bib_block:
                continue

            if bool(re.match(r'^\\(begin|end)\{[a-zA-Z0-9_*]+\}$', stripped)) or stripped.startswith('\\usepackage'):
                continue

            has_letters = bool(re.search(r'[a-zA-Z]{3,}', stripped))
            if has_letters:
                tasks.append((idx, part))

    print(f"Translating {os.path.basename(file_path)}: {len(tasks)} prose paragraphs, {len(caption_tasks)} table/figure captions (workers={max_workers})...")
    results = {}

    if tasks:
        def worker(item):
            i, p = item
            return i, adapter.translate(p, prompt_template)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i, res in executor.map(worker, tasks):
                results[i] = res

    if caption_tasks:
        for idx, part in caption_tasks:
            results[idx] = translate_caption_inside_block(part, adapter, prompt_template)

    translated_parts = []
    for idx, part in enumerate(parts):
        if idx in results:
            translated_parts.append(results[idx])
        else:
            translated_parts.append(part)

    final_content = "".join(translated_parts)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_content)
    print(f"Finished {os.path.basename(file_path)} (Tables 100% preserved).")

def process_latex_project(project_dir, output_zip=None, adapter=None, prompt_template=None, max_workers=4):
    for root, dirs, files in os.walk(project_dir):
        if any(part.startswith('.') for part in root.split(os.sep)):
            continue
        for file in files:
            if file.endswith(".tex") and file not in ["main.tex", "ms.tex", "paper.tex"]:
                file_path = os.path.join(root, file)
                translate_tex_file(file_path, file_path, adapter=adapter, prompt_template=prompt_template, max_workers=max_workers)

    for main_candidate in ["ms.tex", "main.tex", "paper.tex"]:
        cand_path = os.path.join(project_dir, main_candidate)
        if os.path.exists(cand_path):
            translate_tex_file(cand_path, cand_path, adapter=adapter, prompt_template=prompt_template, max_workers=max_workers)
            with open(cand_path, "r", encoding="utf-8", errors="ignore") as f:
                c = f.read()
            if "\\usepackage[UTF8]{ctex}" not in c and "\\usepackage{ctex}" not in c:
                doc_class_match = re.search(r'(\\documentclass(?:\[.*?\])?\{.*?\})', c)
                if doc_class_match:
                    pos = doc_class_match.end()
                    c = c[:pos] + "\n\\usepackage[UTF8]{ctex}\n" + c[pos:]
                else:
                    c = "\\usepackage[UTF8]{ctex}\n" + c
                with open(cand_path, "w", encoding="utf-8") as f:
                    f.write(c)
                print(f"Injected ctex package to {main_candidate}")
            break

    if output_zip:
        print(f"Packing output to {output_zip}...")
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(project_dir):
                for file in files:
                    abs_file = os.path.join(root, file)
                    rel_file = os.path.relpath(abs_file, project_dir)
                    zipf.write(abs_file, rel_file)
        print(f"ZIP package created: {output_zip}")

# ----------------------------------------------------------------------
# 4. 主调度工作流：优先寻找 LaTeX 源码包，实在找不到才降级 PDF
# ----------------------------------------------------------------------

def auto_translate_paper(input_target, output_dir=None, provider="deepseek", max_workers=4,
                         api_key=None, base_url=None, model=None, prompt_template=None, config=None):
    """
    全自动主工作流入口：
    第一优先级：全网检索并下载 arXiv LaTeX 源码工程包，执行出版级保排版精翻（表格绝对冻结仅译 caption）；
    兜底方案：若实在检索不到可用 LaTeX 源码，自动降级为 PDF 版面翻译（pdf2zh-next）。
    """
    env = os.environ.copy()
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"

    adapter = get_adapter(provider=provider, config=config, api_key=api_key, base_url=base_url, model=model)
    prompt_tpl = prompt_template or DEFAULT_PROMPT_TEMPLATE

    print(f"\n=======================================================")
    print(f"[Workflow] 论文全自动翻译启动: {input_target}")
    print(f"[Workflow] 规则准则: 优先寻找/解析 LaTeX 源码包，表格数据 100% 冻结")
    print(f"=======================================================")

    arxiv_id = None
    local_tex_dir = None

    if os.path.isdir(input_target):
        local_tex_dir = os.path.abspath(input_target)
    elif re.search(r'([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)', input_target):
        m = re.search(r'([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)', input_target)
        arxiv_id = m.group(1)
    elif os.path.isfile(input_target) and input_target.lower().endswith(".pdf"):
        print(f"[Workflow] 检查本地 PDF 关联的 arXiv 编号: {input_target}...")
        arxiv_id = find_arxiv_id_from_pdf(input_target)
        if not arxiv_id:
            if fitz:
                try:
                    d = fitz.open(input_target)
                    title = d.metadata.get("title", "")
                    if not title or len(title) < 5:
                        title = d[0].get_text()[:200].split("\n")[0]
                    print(f"[Workflow] 从 PDF 提取标题进行 arXiv 检索: '{title}'...")
                    arxiv_id = search_arxiv_by_title(title)
                except Exception:
                    pass

    # --- 阶段 A：尝试获取并运行 LaTeX 源码工程 ---
    if arxiv_id or local_tex_dir:
        tex_work_dir = local_tex_dir
        if not tex_work_dir:
            temp_name = f"arxiv_{arxiv_id}_src"
            target_source_dir = os.path.join(output_dir or os.getcwd(), temp_name)
            success = fetch_arxiv_source(arxiv_id, target_source_dir)
            if success:
                tex_work_dir = target_source_dir

        if tex_work_dir:
            print(f"[Workflow] >>> 成功获取 LaTeX 源码工程！启用方案 1：LaTeX 出版级精翻模式 <<<")
            print(f"[Workflow] 表格环境 (tabular/table) 数据绝对冻结，仅翻译 \\caption 表题。")
            zip_out = os.path.join(output_dir or os.path.dirname(tex_work_dir), f"{os.path.basename(tex_work_dir)}_zh.zip")
            process_latex_project(tex_work_dir, output_zip=zip_out, adapter=adapter, prompt_template=prompt_tpl, max_workers=max_workers)
            print(f"[Workflow] LaTeX 源码精翻完成！Overleaf 标准工程包已生成: {zip_out}")
            return True

    # --- 阶段 B：未找到 LaTeX 源码，自动降级至 PDF 模式 ---
    print(f"[Workflow] 未发现可用 LaTeX 源码工程，自动平滑降级至方案 2：PDF 版面分析翻译模式。")
    if os.path.isfile(input_target) and input_target.lower().endswith(".pdf"):
        from scripts.pdf_runner import run_pdf_translation
        out_dir = output_dir or os.path.dirname(os.path.abspath(input_target))
        return run_pdf_translation(input_target, out_dir, qps=max_workers, base_url=base_url, api_key=api_key, model=model)
    else:
        print(f"[Workflow] 错误: 既未找到 LaTeX 源码，也未提供有效的本地 PDF 文件进行降级。")
        return False

def main():
    parser = argparse.ArgumentParser(description="Academic Paper Translation Toolkit (Zotero-Prompt Powered & Table Protected)")
    parser.add_argument("--input", help="Auto pipeline: arXiv ID, paper title, or local PDF file / TeX directory")
    parser.add_argument("--arxiv", help="Direct arXiv ID to download and translate")
    parser.add_argument("--dir", help="LaTeX project directory to translate")
    parser.add_argument("--file", help="Single TeX file to translate")
    parser.add_argument("--pdf", help="Direct PDF fallback translate (requires pdf2zh-next)")
    parser.add_argument("--output-dir", help="Output directory for generated files")
    parser.add_argument("--output-zip", help="Path to save the translated project zip")
    parser.add_argument("--provider", default="deepseek", choices=["deepseek", "cpa", "openai", "ollama"], help="LLM provider")
    parser.add_argument("--api-key", help="API key for the chosen provider")
    parser.add_argument("--base-url", help="Base URL for the chosen provider")
    parser.add_argument("--model", help="Model name for the chosen provider")
    parser.add_argument("--prompt-file", help="Custom prompt template file path")
    parser.add_argument("--config", default="config.yaml", help="Path to config file (default: config.yaml)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker threads (default: 4)")
    args = parser.parse_args()

    config = load_config(args.config)
    provider = args.provider
    if not args.provider and "provider" in config:
        provider = config["provider"]

    adapter = get_adapter(provider=provider, config=config, api_key=args.api_key, base_url=args.base_url, model=args.model)
    prompt_tpl = DEFAULT_PROMPT_TEMPLATE
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt_tpl = f.read()

    if args.input:
        auto_translate_paper(args.input, output_dir=args.output_dir, provider=provider,
                             max_workers=args.workers, api_key=args.api_key, base_url=args.base_url,
                             model=args.model, prompt_template=prompt_tpl, config=config)
    elif args.arxiv:
        out_dir = args.output_dir or os.path.abspath(f"arxiv_{args.arxiv}_zh")
        success = fetch_arxiv_source(args.arxiv, out_dir)
        if success:
            zip_out = args.output_zip or os.path.abspath(f"arxiv_{args.arxiv}_zh.zip")
            process_latex_project(out_dir, output_zip=zip_out, adapter=adapter, prompt_template=prompt_tpl, max_workers=args.workers)
    elif args.dir:
        process_latex_project(args.dir, output_zip=args.output_zip, adapter=adapter, prompt_template=prompt_tpl, max_workers=args.workers)
    elif args.file:
        translate_tex_file(args.file, adapter=adapter, prompt_template=prompt_tpl, max_workers=args.workers)
    elif args.pdf:
        from scripts.pdf_runner import run_pdf_translation
        out_dir = args.output_dir or os.path.dirname(os.path.abspath(args.pdf))
        run_pdf_translation(args.pdf, out_dir, qps=args.workers, base_url=args.base_url, api_key=args.api_key, model=args.model)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
