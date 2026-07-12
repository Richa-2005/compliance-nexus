from .config import settings
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.language_models.chat_models import BaseChatModel

def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    provider = settings.LLM_PROVIDER.strip().upper()
    if provider == "OLLAMA":
        return ChatOllama(
            model="llama3.1",
            temperature=temperature,
            base_url=settings.OLLAMA_BASE_URL
        )
    
    if provider == "GROQ":
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=temperature,
            api_key=settings.GROQ_API_KEY
        )
    
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER!r}. "
        "Expected 'OLLAMA' or 'GROQ'."
    )
