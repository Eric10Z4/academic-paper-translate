import os
from .openai_compatible import OpenAICompatibleAdapter


class CPAAdapter(OpenAICompatibleAdapter):
    def __init__(self,base_url=None,api_key=None,model=None,timeout=90,attempts=3):
        super().__init__(base_url or os.getenv('CPA_BASE_URL','http://127.0.0.1:8317/v1'),
                         api_key if api_key is not None else os.getenv('CPA_API_KEY',''),
                         model or os.getenv('CPA_MODEL','gemini-3.8-flash-high'),timeout,attempts)
