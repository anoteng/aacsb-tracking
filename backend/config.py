from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import quote_plus


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "aol"
    db_user: str = "aol"
    db_password: str = "yamnZ@2iFdE*OL2hd16q"

    # Authentication
    secret_key: str = "change-this-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 1 week
    magic_link_expire_minutes: int = 15

    # Email
    smtp_host: str = "smtp-nat.nmbu.no"
    smtp_port: int = 25
    smtp_start_tls: bool = True
    smtp_skip_verify: bool = True  # Skip cert verification for internal SMTP
    email_from: str = "noreply@nmbu.no"

    # App
    app_name: str = "AACSB Accreditation"
    app_url: str = "https://hh-utdanning.nmbu.no/aacsb"
    debug: bool = False

    # Google OAuth (optional)
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # NVA API (Norwegian Research Archive)
    nva_client_id: str | None = None
    nva_client_secret: str | None = None
    nva_token_url: str = "https://nva-prod-ext.auth.eu-west-1.amazoncognito.com/oauth2/token"
    nva_api_url: str = "https://api.nva.unit.no"

    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        return f"mysql+pymysql://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
