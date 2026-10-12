import os
from .openai_compatible import OpenAICompatibleAdapter


class OllamaAdapter(OpenAICompatibleAdapter):
    def __init__(self,base_url=None,api_key=None,model=None,timeout=120,attempts=3):
        super().__init__(base_url or os.getenv('OLLAMA_BASE_URL','http://127.0.0.1:11434/v1'),
                         api_key if api_key is not None else os.getenv('OLLAMA_API_KEY','ollama'),
                         model or os.getenv('OLLAMA_MODEL','qwen2.5:14b'),timeout,attempts)
