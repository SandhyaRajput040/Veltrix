"""
Centralized application configuration.

This module is the ONLY place that reads environment variables. Every
other module in the project should import `settings` from here instead
of calling `os.environ` directly. That keeps configuration, business
logic, and external integrations cleanly separated (see project rules).

No secrets, passwords, or API keys are ever hard-coded here -- values
come from environment variables, which are loaded from a local `.env`
file during development (see `.env.example`) and from the host's secret
manager in production.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load variables from a local .env file (if one exists) into the process
# environment. In production, environment variables are injected by the
# host directly, so this call is harmless there (it just finds no file).
load_dotenv()


def _get_env(name: str, default: str = "") -> str:
    """Read a string environment variable, returning `default` if unset."""
    return os.environ.get(name, default)


def _get_bool_env(name: str, default: bool = False) -> bool:
    """Read an environment variable as a boolean (accepts true/1/yes/on)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_int_env(name: str, default: int) -> int:
    """Read an environment variable as an int, falling back to `default`."""
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    """
    Immutable snapshot of application configuration.

    Every field maps directly to a variable documented in `.env.example`.
    Fields are plain strings/ints/bools -- this class does NOT validate
    that a value is present or correct. Each module validates the
    specific values it needs when that module is built (for example,
    the Amazon module will check AMAZON_* fields when Module 4 is
    implemented). Module 1 only needs configuration LOADING to work.
    """

    # Application
    app_name: str
    environment: str
    debug: bool

    # Amazon
    amazon_access_key: str
    amazon_secret_key: str
    amazon_marketplace_id: str
    amazon_seller_id: str

    # Baapstore
    baapstore_api_url: str
    baapstore_api_key: str

    # Google Drive
    google_drive_credentials_file: str

    # Notifications
    notification_email: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str


def load_settings() -> Settings:
    """Build a fresh Settings snapshot from the current environment."""
    return Settings(
        app_name=_get_env("APP_NAME", "Veltrix"),
        environment=_get_env("ENVIRONMENT", "development"),
        debug=_get_bool_env("DEBUG", False),
        amazon_access_key=_get_env("AMAZON_ACCESS_KEY"),
        amazon_secret_key=_get_env("AMAZON_SECRET_KEY"),
        amazon_marketplace_id=_get_env("AMAZON_MARKETPLACE_ID"),
        amazon_seller_id=_get_env("AMAZON_SELLER_ID"),
        baapstore_api_url=_get_env("BAAPSTORE_API_URL"),
        baapstore_api_key=_get_env("BAAPSTORE_API_KEY"),
        google_drive_credentials_file=_get_env("GOOGLE_DRIVE_CREDENTIALS_FILE"),
        notification_email=_get_env("NOTIFICATION_EMAIL"),
        smtp_host=_get_env("SMTP_HOST"),
        smtp_port=_get_int_env("SMTP_PORT", 587),
        smtp_username=_get_env("SMTP_USERNAME"),
        smtp_password=_get_env("SMTP_PASSWORD"),
    )


# Module-level singleton so the rest of the codebase can simply do:
#   from src.config.settings import settings
settings = load_settings()