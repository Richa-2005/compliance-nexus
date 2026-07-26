from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
class Settings(BaseSettings):
    
    LLM_PROVIDER: str
    GROQ_API_KEY: SecretStr  # Hides the value when printed or dumped to logs
    OLLAMA_BASE_URL: str

    model_config = SettingsConfigDict(
        env_file="/Users/richagupta/Documents/compliance-nexus/backend/.env",
        env_file_encoding="utf-8",
        extra="ignore"  
    )

    PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
    DB_DIR: Path = PROJECT_ROOT / "data" / "processed"

    STATES_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "eval_states.json"
    PROGRESS_FILE = PROJECT_ROOT / "data" / "processed" / "eval_progress.json"

    PROGRESS_FILE = PROJECT_ROOT / "data" / "processed" / "eval_progress.json"
    REPORT_OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "eval_results.md"


settings = Settings()

