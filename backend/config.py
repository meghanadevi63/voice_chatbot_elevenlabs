from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _labels(pairs: str) -> dict[str, str]:
    """Parse "id:Label,id2:Label2" into {id: label}; the label defaults to the id."""
    parts = (p.split(":", 1) for p in pairs.split(",") if p.strip())
    return {p[0].strip(): (p[1] if len(p) > 1 else p[0]).strip() for p in parts}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    # Default answer model; always allowed even if missing from llm_models
    groq_model: str = "openai/gpt-oss-20b"
    # Answer models the user may pick (comma-separated; "model_id:Label" sets a display name)
    llm_models: str = "openai/gpt-oss-20b,openai/gpt-oss-120b"
    # Small, fast model used only to classify intent before retrieval
    router_model: str = "openai/gpt-oss-20b"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    milvus_db_path: str = "./data/milvus.db"
    collection_name: str = "docs_rag"
    docs_dir: str = "./docs"

    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 4

    elevenlabs_api_key: str = ""
    stt_model: str = "scribe_v2"
    # Upper bound for one push-to-talk recording upload
    max_audio_mb: int = 10

    # Allow-listed TTS models, same format as llm_models; the first is the default
    tts_models: str = "eleven_v4_turbo,eleven_v3_conversational"
    # Premade "Matilda" until a default is picked by ear
    default_voice_id: str = "XrExE9yKIg1WjnnlVkGX"
    # Longer answers are cut at a sentence boundary (0.5 credit/char on both models)
    max_tts_chars: int = 800
    # Dev-only cache of generated audio so replays cost no credits; empty disables it
    tts_cache_dir: str = "./data/tts_cache"

    # Hands-free: ElevenLabs calls {public_base_url}/v1/chat/completions with this bearer
    # secret. Empty secret disables the endpoint.
    custom_llm_secret: str = ""
    # Public URL of this backend (ngrok dev domain during development), no trailing slash
    public_base_url: str = ""

    # Comma-separated origins allowed to call the API directly from a browser.
    # Only needed when the frontend is served from a different origin.
    cors_origins: str = "https://localhost:5174,https://127.0.0.1:5174"

    def tts_model_labels(self) -> dict[str, str]:
        return _labels(self.tts_models)

    def llm_model_labels(self) -> dict[str, str]:
        labels = _labels(self.llm_models)
        return labels if self.groq_model in labels else {self.groq_model: self.groq_model, **labels}


@lru_cache
def get_settings() -> Settings:
    return Settings()
