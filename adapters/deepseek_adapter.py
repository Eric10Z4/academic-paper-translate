import json
import urllib.request
from .base import BaseLLMAdapter

class DeepSeekAdapter(BaseLLMAdapter):
    """
    Adapter for DeepSeek API (deepseek-chat / deepseek-reasoner).
    """
    def __init__(self, base_url="https://api.deepseek.com/v1", api_key="", model="deepseek-chat", timeout=60):
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
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
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
