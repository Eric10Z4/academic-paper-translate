from abc import ABC, abstractmethod

class BaseLLMAdapter(ABC):
    @abstractmethod
    def translate(self, text: str, prompt_template: str) -> str:
        """Translate a single paragraph or block using the specified prompt template."""
        pass
