"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_maps_api_key: str = ""
    anthropic_api_key: str = ""

    # Google Maps defaults
    satellite_zoom: int = 20
    satellite_size: str = "640x640"
    streetview_fov: int = 90
    streetview_pitch: int = 10
    streetview_size: str = "640x640"

    # Claude Vision model
    claude_model: str = "claude-sonnet-4-5-20250929"

    # Default building assumptions
    default_storey_height: float = 3.0  # meters
    default_air_changes_per_hour: float = 0.5
    default_occupancy_area: float = 52.0  # m² per person


def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
