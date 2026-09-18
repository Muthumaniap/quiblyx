from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    product_name: str = "Quilblyx"
    database_url: str = "postgresql+psycopg://platform:local-only@localhost:5432/platform"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    dev_identity: bool = False
    dev_login_token: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = "platform"
    oidc_jwks_url: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    web_origin: str = "http://localhost:3000"

    @model_validator(mode="after")
    def validate_credentials(self):
        Fernet(self.secret_key.encode())
        if self.dev_identity and not self.dev_login_token:
            raise ValueError("Development identity requires a generated DEV_LOGIN_TOKEN")
        if not self.dev_identity:
            if not self.oidc_issuer.startswith("https://") or not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("Non-development mode requires HTTPS OIDC issuer and JWKS")
        return self


@lru_cache
def settings():
    return Settings()
