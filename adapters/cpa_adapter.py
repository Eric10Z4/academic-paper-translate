import json
import urllib.request
from .base import BaseLLMAdapter

class CPAAdapter(BaseLLMAdapter):
    """
    Adapter for local CPA (Cherry Studio / Antigravity proxy),
    typically providing free access to Gemini 3.8 Flash High.
    """
    def __init__(self, base_url="http://127.0.0.1:8317/v1", api_key="sk-eric10z4", model="gemini-3.8-flash-high", timeout=60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def translate(self, text: str, prompt_template: str) -> str:
        prompt = prompt_template.replace("__SOURCE_TEXT__", text)
        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
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
