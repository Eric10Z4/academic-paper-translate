import os
import sys
import re
import json
import urllib.request
import zipfile
import tarfile
import argparse
from concurrent.futures import ThreadPoolExecutor

try:
    from adapters.deepseek_adapter import DeepSeekAdapter
    from adapters.openai_adapter import OpenAIAdapter
    from adapters.ollama_adapter import OllamaAdapter
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adapters.deepseek_adapter import DeepSeekAdapter
    from adapters.openai_adapter import OpenAIAdapter
    from adapters.ollama_adapter import OllamaAdapter

DEFAULT_PROMPT_TEMPLATE = """As an academic expert with specialized knowledge in various fields, please provide a proficient and precise translation from English to Simplified Chinese of the academic text enclosed in 🔤. It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. Keep all LaTeX markup, math notation ($...$, equations), citations (\\cite{...}), references (\\ref{...}), and environment tags intact. Translate only the natural language text. The text is as follows:

🔤 __SOURCE_TEXT__ 🔤

Please provide the translated result without any additional explanation and remove 🔤."""

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

    # Defaults from CLI args or environment variables
    if provider == "deepseek":
        b_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        mod = model or "deepseek-chat"
        return DeepSeekAdapter(base_url=b_url, api_key=key, model=mod)
    elif provider == "ollama":
        b_url = base_url or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434/v1")
        mod = model or "qwen2.5:14b"
        return OllamaAdapter(base_url=b_url, api_key="ollama", model=mod)
    else: # openai
        b_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        mod = model or "gpt-4o-mini"
        return OpenAIAdapter(base_url=b_url, api_key=key, model=mod)

def split_into_paragraphs(tex_content):
    return re.split(r'(\n\s*\n+)', tex_content)

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
    for idx, part in enumerate(parts):
        if idx % 2 == 0:
            stripped = part.strip()
            has_letters = bool(re.search(r'[a-zA-Z]{3,}', stripped))
            is_pure_comment = stripped.startswith('%')
            is_pure_env_header = bool(re.match(r'^\\(begin|end)\{[a-zA-Z0-9_*]+\}$', stripped))
            is_pure_usepackage = bool(re.match(r'^\\usepackage.*\}$', stripped))
            if has_letters and not is_pure_comment and not is_pure_env_header and not is_pure_usepackage:
                tasks.append((idx, part))

    print(f"Translating {os.path.basename(file_path)}: {len(tasks)} prose paragraphs (workers={max_workers})...")
    results = {}
    if tasks:
        def worker(item):
            i, p = item
            return i, adapter.translate(p, prompt_template)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for i, res in executor.map(worker, tasks):
                results[i] = res

    translated_parts = []
    for idx, part in enumerate(parts):
        if idx in results:
            translated_parts.append(results[idx])
        else:
            translated_parts.append(part)

    final_content = "".join(translated_parts)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_content)
    print(f"Finished {os.path.basename(file_path)}.")

def fetch_arxiv_source(arxiv_id, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    tar_path = os.path.join(target_dir, f"{arxiv_id}.tar.gz")
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    print(f"Downloading arXiv source from {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp, open(tar_path, 'wb') as out_f:
        out_f.write(resp.read())
    
    print("Extracting source package...")
    with tarfile.open(tar_path, "r:*") as tar:
        tar.extractall(path=target_dir)
    os.remove(tar_path)
    print(f"arXiv source extracted to {target_dir}")

def process_latex_project(project_dir, output_zip=None, adapter=None, prompt_template=None, max_workers=4):
    for root, dirs, files in os.walk(project_dir):
        if any(part.startswith('.') for part in root.split(os.sep)):
            continue
        for file in files:
            if file.endswith(".tex"):
                file_path = os.path.join(root, file)
                translate_tex_file(file_path, file_path, adapter=adapter, prompt_template=prompt_template, max_workers=max_workers)

    for main_candidate in ["ms.tex", "main.tex", "paper.tex"]:
        cand_path = os.path.join(project_dir, main_candidate)
        if os.path.exists(cand_path):
            with open(cand_path, "r", encoding="utf-8", errors="ignore") as f:
                c = f.read()
            if "\\usepackage[UTF8]{ctex}" not in c and "\\usepackage{ctex}" not in c:
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

def main():
    parser = argparse.ArgumentParser(description="Academic Paper Translation Toolkit (Zotero-Prompt Powered)")
    parser.add_argument("--arxiv", help="arXiv paper ID (e.g. 2201.02609) to download and translate")
    parser.add_argument("--dir", help="LaTeX project directory to translate")
    parser.add_argument("--file", help="Single TeX/text file to translate")
    parser.add_argument("--pdf", help="Translate local PDF file directly (requires pdf2zh-next)")
    parser.add_argument("--output-dir", help="Output directory for generated files")
    parser.add_argument("--output-zip", help="Path to save the translated project zip")
    parser.add_argument("--provider", default="deepseek", choices=["deepseek", "openai", "ollama"], help="LLM provider")
    parser.add_argument("--api-key", help="API key for the chosen provider")
    parser.add_argument("--base-url", help="Base URL for the chosen provider")
    parser.add_argument("--model", help="Model name for the chosen provider")
    parser.add_argument("--prompt-file", help="Custom prompt template file path")
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker threads (default: 4)")
    args = parser.parse_args()

    adapter = get_adapter(args.provider, api_key=args.api_key, base_url=args.base_url, model=args.model)
    prompt_tpl = DEFAULT_PROMPT_TEMPLATE
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt_tpl = f.read()

    if args.pdf:
        from scripts.pdf_runner import run_pdf_translation
        out_dir = args.output_dir or os.path.dirname(os.path.abspath(args.pdf))
        run_pdf_translation(args.pdf, out_dir, qps=args.workers)
    elif args.file:
        translate_tex_file(args.file, adapter=adapter, prompt_template=prompt_tpl, max_workers=args.workers)
    elif args.arxiv:
        out_dir = args.output_dir or os.path.abspath(f"arxiv_{args.arxiv}_zh")
        fetch_arxiv_source(args.arxiv, out_dir)
        zip_out = args.output_zip or os.path.abspath(f"arxiv_{args.arxiv}_zh.zip")
        process_latex_project(out_dir, output_zip=zip_out, adapter=adapter, prompt_template=prompt_tpl, max_workers=args.workers)
    elif args.dir:
        process_latex_project(args.dir, output_zip=args.output_zip, adapter=adapter, prompt_template=prompt_tpl, max_workers=args.workers)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
