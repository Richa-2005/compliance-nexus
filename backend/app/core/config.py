from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    
    LLM_PROVIDER: str
    GROQ_API_KEY: SecretStr  # Hides the value when printed or dumped to logs
    OLLAMA_BASE_URL: str
    JWT_SECRET_KEY : SecretStr
    JWT_ALGORITHM:str
    model_config = SettingsConfigDict(
        env_file="/Users/richagupta/Documents/compliance-nexus/backend/.env",
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

    NODE_TO_DOC = {
        "Apple SEC Filings": "apple-SEC.pdf",
        "RBI Credit Risk": "credit_Risk_RBI.pdf",
        "Foreign Investment": "foreign_Investement_rbi.pdf",
        "RBI KYC": "kyc_rbi.pdf",
        "Microsoft SEC Filings": "microsoft-SEC.pdf",
        "Internal Policy": "nexus_holdings_global_inc.pdf",
    }

    DOC_TO_NODE = {doc: node for node, doc in NODE_TO_DOC.items()}

    EVIDENCE_SELECTION_CRITERIA = {
        "direct_threshold_rule_match": 80,
        "primary_source_match": 20,
        "ceiling_value_match": 30,
        "transaction_fact_match": 15,
        "rule_language_match": 10,
    }

    RULE_LANGUAGE_TERMS = {
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

