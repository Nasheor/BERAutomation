"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_parse_none_str="none",
    )

    google_maps_api_key: str = ""
    mapbox_access_token: str = ""
    anthropic_api_key: str = ""
    mistral_api_key: str = ""

    # Vision model provider used when none is chosen: "claude" or "mistral"
    llm_provider: str = "claude"

    # Google Maps defaults
    satellite_zoom: int = 20
    satellite_size: str = "640x640"
    streetview_fov: int = 90
    streetview_pitch: int = 10
    streetview_size: str = "640x640"

    # Claude Vision model
    claude_model: str = "claude-sonnet-5-5"
    # Sampling temperature. None omits the parameter, which current models (Sonnet 5+,
    # Opus 4.7+) require — they reject temperature with a 400. Only set a value (e.g.
    # CLAUDE_TEMPERATURE=0) when claude_model is an older model that still accepts it.
    claude_temperature: float | None = None

    # Mistral vision model: a fixed model ID (not "-latest"), so every run of the study
    # uses the same model. Mistral Large 4 (checked with GET /v1/models, Nov 2026).
    mistral_model: str = "mistral-large-4-0"
    # None = Mistral's default sampling, like Claude (whose current models refuse a
    # temperature), so both models run as shipped. A value (e.g. 0) also sends top_p=1.
    mistral_temperature: float | None = None
    # How long the model reasons before answering. Mistral Large 4 accepts "low",
    # "medium" or "high" (it cannot switch reasoning off); None leaves Mistral's default.
    # "low": at the default level the Street View, satellite and description requests sent
    # nothing back for over 7 minutes (Nov 2026); at "low" they answer in 10 to 20 s.
    mistral_reasoning_effort: str | None = "low"

    # Default building assumptions
    default_storey_height: float = 3.0  # meters
    default_air_changes_per_hour: float = 0.5
    default_occupancy_area: float = 52.0  # m² per person


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
