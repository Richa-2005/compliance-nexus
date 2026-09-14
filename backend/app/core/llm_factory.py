from .config import settings
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.language_models.chat_models import BaseChatModel

def get_chat_model(
    temperature: float = 0.0,
    max_tokens: int | None = None,
    task: str = "default",
) -> BaseChatModel:
    provider = settings.LLM_PROVIDER.strip().upper()
    if provider == "OLLAMA":
        return ChatOllama(
            model="llama3.1",
            temperature=temperature,
            base_url=settings.OLLAMA_BASE_URL
        )
    
    if provider == "GROQ":
        model = settings.GROQ_MODEL
        api_key = settings.GROQ_API_KEY
        if task == "extraction":
            model = settings.GROQ_EXTRACTION_MODEL or model
            api_key = settings.GROQ_EXTRACTION_API_KEY or api_key
        elif task == "rationale":
            model = settings.GROQ_RATIONALE_MODEL or model
            api_key = settings.GROQ_RATIONALE_API_KEY or api_key

        return ChatGroq(
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_tokens=max_tokens,
            reasoning_format=settings.GROQ_REASONING_FORMAT,
        )
    
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER!r}. "
        "Expected 'OLLAMA' or 'GROQ'."
    )
