import os
from .openai_compatible import OpenAICompatibleAdapter


class DeepSeekAdapter(OpenAICompatibleAdapter):
    def __init__(self,base_url=None,api_key=None,model=None,timeout=90,attempts=3):
        super().__init__(base_url or os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com/v1'),
                         api_key if api_key is not None else os.getenv('DEEPSEEK_API_KEY',''),
                         model or os.getenv('DEEPSEEK_MODEL','deepseek-chat'),timeout,attempts)
