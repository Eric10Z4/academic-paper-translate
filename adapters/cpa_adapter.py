import os
import json
import urllib.request
from .base import BaseLLMAdapter

class CPAAdapter(BaseLLMAdapter):
    """
    Adapter for local CPA (Cherry Studio / Antigravity proxy),
    typically providing free access to Gemini 3.8 Flash High.
    """
    def __init__(self, base_url=None, api_key=None, model=None, timeout=60):
        self.base_url = (base_url or os.environ.get("CPA_BASE_URL", "http://127.0.0.1:8317/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("CPA_API_KEY", "")
        self.model = model or os.environ.get("CPA_MODEL", "gemini-3.8-flash-high")
        self.timeout = timeout

    def translate(self, text: str, prompt_template: str) -> str:
        prompt = prompt_template.replace("__SOURCE_TEXT__", text)
        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            headers=headers,
            data=json.dumps(data).encode("utf-8")
        )
        # Force bypassing local proxy to avoid 502 loop on Windows
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open(req, timeout=self.timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            ans = res["choices"][0]["message"]["content"].strip()
            ans = ans.replace("🔤", "").strip()
            if ans.startswith("```latex"):
                ans = ans[len("```latex"):].strip()
            if ans.startswith("```"):
                ans = ans[len("```"):].strip()
            if ans.endswith("```"):
                ans = ans[:-3].strip()
            return ans
