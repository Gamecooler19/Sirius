"""Application settings, read once from the environment.

Every value here is required at startup except where a default is given.
As of this module, these values are injected by Docker Compose's `${VAR}`
interpolation from `deploy/.env` directly into each service's
`environment:` block -- there is no `.env` file inside any container.
`env_file=".env"` below is a harmless fallback for running pytest locally
outside Compose; pydantic-settings only uses it if the file exists.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres via PgBouncer (transaction pooling) -- used by the app at request time.
    DATABASE_URL: str

    # Postgres direct connection -- used by Alembic only, bypassing PgBouncer,
    # because DDL and advisory locks need session continuity that transaction
    # pooling does not provide (ADR-01).
    DATABASE_DIRECT_URL: str

    # Valkey (session store, TOTP-enrollment-in-progress state).
    VALKEY_URL: str

    # RustFS (S3-compatible object storage) -- provisioned for future Excel
    # import artefact storage; not read by any request-path code in this
    # module.
    RUSTFS_ENDPOINT: str
    RUSTFS_ACCESS_KEY: str
    RUSTFS_SECRET_KEY: str
    RUSTFS_BUCKET: str

    # Comma-separated list of allowed browser origins for CORS. No wildcard,
    # since allow_credentials=True (the session cookie).
    CORS_ORIGINS: str = "http://localhost:5173"

    # Whether the session cookie carries the Secure attribute. Must be
    # False for local plain-HTTP development (no browser stores a Secure
    # cookie over plain HTTP) and True for any real deployment.
    SESSION_COOKIE_SECURE: bool = False

    # Fernet key encrypting session payload fields at rest in Valkey.
    SESSION_ENCRYPTION_KEY: str

    # Fernet key encrypting TOTP secrets at rest in Postgres
    # (user.totp_secret_encrypted).
    TOTP_ENCRYPTION_KEY: str

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Module 16: real SMTP server (Mailpit, local dev only -- see
    # deploy/docker-compose.yml's own `mailpit` service). No external
    # provider, no API key: `smtplib` connects to this host:port directly.
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_FROM_ADDRESS: str = "no-reply@sirius.app"

    # Origin the password-reset link in that email points at -- the
    # frontend dev server's own published address, not this API's own.
    FRONTEND_BASE_URL: str = "http://127.0.0.1:5173"

    # Module 20: real Web Push (RFC 8292 VAPID) signing keys. Generated
    # once per deployment (see `deploy/.env.example`'s own generation
    # command), never committed -- the private key signs every outbound
    # push, and a leaked one lets an attacker impersonate this server to
    # any push service that has ever seen the matching public key.
    # `VAPID_SUBJECT` is the "who to contact about this traffic" claim
    # every push service requires (RFC 8292's own `sub` claim) -- a
    # `mailto:` URI, the same convention `pywebpush`'s own documentation
    # and every real deployment guide uses, not a made-up format.
    VAPID_PRIVATE_KEY: str
    VAPID_PUBLIC_KEY: str
    VAPID_SUBJECT: str = "mailto:no-reply@sirius.app"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
