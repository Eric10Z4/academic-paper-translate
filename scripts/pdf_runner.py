import os
import subprocess
import sys

def run_pdf_translation(pdf_path, output_dir, dual=True, mono=True, qps=5, custom_prompt=None):
    """
    Execute pdf2zh-next with Zotero academic translation prompt & local CPA/OpenAI endpoint.
    """
    if custom_prompt is None:
        custom_prompt = (
            "As an academic expert with specialized knowledge in various fields, "
            "please provide a proficient and precise translation from English to Simplified Chinese of the academic text. "
            "It is crucial to maintaining the original phrase or sentence and ensure accuracy while utilizing the appropriate language. "
            "Please provide the translated result without any additional explanation."
        )

    cmd = [
        "uv.exe" if sys.platform == "win32" else "uv",
        "tool", "run", "--from", "pdf2zh-next", "pdf2zh_next",
        pdf_path,
        "--openaicompatible",
        "--openai-compatible-base-url", "http://127.0.0.1:8317/v1",
        "--openai-compatible-api-key", "sk-eric10z4",
        "--openai-compatible-model", "gemini-3.8-flash-high",
        "--no-auto-extract-glossary",
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

    print(f"[pdf_runner] Executing PDF translation on {pdf_path}...")
    proc = subprocess.run(cmd, env=env)
    return proc.returncode == 0
