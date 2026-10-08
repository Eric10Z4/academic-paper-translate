import os
import subprocess
import sys

def run_pdf_translation(pdf_path, output_dir, dual=True, mono=True, qps=5, custom_prompt=None,
                        base_url=None, api_key=None, model=None):
    """
    Execute pdf2zh-next with Zotero academic translation prompt & OpenAI/CPA compatible endpoint.
    """
    if custom_prompt is None:
        custom_prompt = (
            "As an academic expert with specialized knowledge in various fields, "
            "please provide a proficient and precise translation from English to Simplified Chinese of the academic text. "
            "It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. "
            "Please provide the translated result without any additional explanation."
        )

    base_url = base_url or os.environ.get("OPENAI_BASE_URL", os.environ.get("CPA_BASE_URL", "http://127.0.0.1:8317/v1"))
    api_key = api_key or os.environ.get("OPENAI_API_KEY", os.environ.get("CPA_API_KEY", ""))
    model = model or os.environ.get("OPENAI_MODEL", os.environ.get("CPA_MODEL", "gemini-3.8-flash-high"))

    cmd = [
        "uv.exe" if sys.platform == "win32" else "uv",
        "tool", "run", "--from", "pdf2zh-next", "pdf2zh_next",
        pdf_path,
        "--openaicompatible",
        "--openai-compatible-base-url", base_url,
        "--openai-compatible-api-key", api_key or "sk-dummy",
        "--openai-compatible-model", model,
        "--no-auto-extract-glossary",
        "--figure-table-protection-threshold", "0.1",
        "--qps", str(qps),
        "--lang-in", "en",
        "--lang-out", "zh-CN",
        "--custom-system-prompt", custom_prompt,
        "--output", output_dir
    ]

    if not dual:
        cmd.append("--no-dual")
    if not mono:
        cmd.append("--no-mono")

    env = os.environ.copy()
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"

    print(f"[pdf_runner] Executing PDF translation on {pdf_path} via {base_url} ({model})...")
    proc = subprocess.run(cmd, env=env)
    return proc.returncode == 0
