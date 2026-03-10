from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "TrackForge"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Database
    database_url: str = "postgresql+asyncpg://trackforge:trackforge@db:5432/trackforge"
    database_url_sync: str = "postgresql+psycopg2://trackforge:trackforge@db:5432/trackforge"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Auth
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Search cache TTLs (seconds)
    cache_ttl_artist: int = 60 * 60 * 24 * 7   # 7 days
    cache_ttl_search: int = 60 * 60 * 24        # 24 hours

    # Import pipeline
    import_auto_threshold: float = 0.85
    staging_path: str = "/staging"
    library_path: str = "/library"
    # Folder naming pattern for library imports.
    # Variables: {artist}, {album}, {year}
    # Default nests under artist folder: Artist/Album [Year]
    library_folder_pattern: str = "{artist}/{album} [{year}]"

    # Jellyfin
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    # MusicBrainz
    musicbrainz_app_name: str = "TrackForge"
    musicbrainz_app_version: str = "0.1.0"
    musicbrainz_contact: str = ""

    # Discogs
    discogs_token: str = ""

    # Spotify
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # Discord
    discord_webhook_url: str = ""

    # Fanart.tv
    fanart_api_key: str = ""

    # AcoustID
    acoustid_api_key: str = ""

    # Acquisition
    slskd_url: str = ""
    slskd_api_key: str = ""

    qbittorrent_url: str = ""
    qbittorrent_username: str = ""
    qbittorrent_password: str = ""

    nzbget_url: str = ""
    nzbget_username: str = ""
    nzbget_password: str = ""
    nzbget_category: str = "music"
    # Path inside the worker container where NZBGet's complete/music dir is mounted
    nzbget_complete_path: str = ""

    prowlarr_url: str = ""
    prowlarr_api_key: str = ""

    sabnzbd_url: str = ""
    sabnzbd_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
