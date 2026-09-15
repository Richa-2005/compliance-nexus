from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import ClassVar

class Settings(BaseSettings):
    
    LLM_PROVIDER: str = "OLLAMA"
    GROQ_API_KEY: SecretStr = SecretStr("")  # Hides the value when printed or dumped to logs
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_EXTRACTION_API_KEY: SecretStr | None = None
    GROQ_EXTRACTION_MODEL: str | None = None
    GROQ_RATIONALE_API_KEY: SecretStr | None = None
    GROQ_RATIONALE_MODEL: str | None = None
    GROQ_REASONING_FORMAT: str = "hidden"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    JWT_SECRET_KEY : SecretStr = SecretStr("local-development-secret")
    JWT_ALGORITHM:str = "HS256"
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,https://compliance-nexus.vercel.app"
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore"  
    )

    PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
    DB_DIR: Path = PROJECT_ROOT / "data" / "processed"

    STATES_OUTPUT_FILE : Path = PROJECT_ROOT / "data" / "processed" / "eval_states.json"
    PROGRESS_FILE :Path = PROJECT_ROOT / "data" / "processed" / "eval_progress.json"

    PROGRESS_FILE : Path = PROJECT_ROOT / "data" / "processed" / "eval_progress.json"
    REPORT_OUTPUT_FILE : Path = PROJECT_ROOT / "data" / "processed" / "eval_results.md"

    API_V1_PREFIX: str = "/api/v1"

    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_CONSUMER_GROUP: str = "compliance-nexus-ingestion"
    KAFKA_DOCUMENT_INGESTED_TOPIC: str = "document.ingested"
    KAFKA_DOCUMENT_PARSED_TOPIC: str = "document.parsed"
    KAFKA_EMBEDDING_CREATED_TOPIC: str = "embedding.created"
    KAFKA_AUDIT_REQUESTED_TOPIC: str = "audit.requested"
    KAFKA_AUDIT_COMPLETED_TOPIC: str = "audit.completed"
    KAFKA_DEAD_LETTER_TOPIC: str = "document.dead_letter"
    KAFKA_MAX_RETRIES: int = 3
    INGESTION_DIR: Path = PROJECT_ROOT / "data" / "ingestion"

    @property
    def cors_origins(self) -> list[str]:
        origins = {
            origin.strip().rstrip("/")
            for origin in self.BACKEND_CORS_ORIGINS.split(",")
            if origin.strip()
        }
        origins.add("https://compliance-nexus.vercel.app")
        return sorted(origins)

    NODE_TO_DOC: ClassVar[dict[str, str]] = {
        "Apple SEC Filings": "apple-SEC.pdf",
        "RBI Credit Risk": "credit_Risk_RBI.pdf",
        "Foreign Investment": "foreign_Investement_rbi.pdf",
        "RBI KYC": "kyc_rbi.pdf",
        "Microsoft SEC Filings": "microsoft-SEC.pdf",
        "Internal Policy": "nexus_holdings_global_inc.pdf",
    }

    DOC_TO_NODE: ClassVar[dict[str, str]] = {doc: node for node, doc in NODE_TO_DOC.items()}

    EVIDENCE_SELECTION_CRITERIA: ClassVar[dict[str, int]] = {
        "direct_threshold_rule_match": 80,
        "primary_source_match": 20,
        "ceiling_value_match": 30,
        "transaction_fact_match": 15,
        "rule_language_match": 10,
    }

    RULE_LANGUAGE_TERMS: ClassVar[set[str]] = {
        "cap",
        "capped",
        "ceiling",
        "limit",
        "threshold",
        "remittance",
        "approval",
        "prohibited",
        "required",
        "compliance",
    }

settings = Settings()
