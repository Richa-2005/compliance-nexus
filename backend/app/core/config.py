from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    
    LLM_PROVIDER: str
    GROQ_API_KEY: SecretStr  # Hides the value when printed or dumped to logs
    OLLAMA_BASE_URL: str

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        extra="ignore"  
    )

settings = Settings()

