"""Settings from environment variables (pydantic-settings). No secret has a default.

Phase 2 and 3 features sit behind the `feature_*` flags, all off by default, so switching them
off always returns Phase 1 behaviour.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
NAIRA = 100  # kobo per naira


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore", case_sensitive=False)

    # --- required, no defaults ---
    database_url: str = Field(description="postgresql+asyncpg://user:pass@host:5432/db")
    session_secret: str = Field(min_length=32, description="Signs session cookies")

    # --- passkeys: the RP ID must be the registrable domain the phone's passkey is bound to ---
    rp_id: str = "localhost"
    rp_name: str = "Zolo"
    origin: str = "http://localhost:3000"  # exact origin the browser reports; comma list allowed
    cors_origins: str = "http://localhost:3000"

    # --- environment ---
    env: str = "dev"  # dev | test | prod
    log_level: str = "INFO"
    cookie_secure: bool = True  # Secure cookies (HTTPS). Turn off only for plain-http localhost.

    # --- passkeys: signature counter ---
    # True (default): the counter must strictly increase once it is non-zero, so an equal count
    # (a possible cloned authenticator) is refused. False (demo only): an equal non-zero count is
    # allowed and logged as a warning. A count that goes BACKWARDS is refused in both modes.
    webauthn_strict_counter: bool = True

    # --- consent ---
    request_ttl_seconds: int = 120
    session_ttl_seconds: int = 12 * 60 * 60
    mock_otp: str = "123456"  # the fixed OTP for mock login (Phases 1 and 2)

    # --- mock bank ---
    mock_bank_code: str = "057"  # the bank Zolo sits in front of; from_account lives here
    mock_bank_latency_min_ms: int = 300
    mock_bank_latency_max_ms: int = 800

    # --- risk (Phase 1): hard caps, in kobo ---
    per_payment_cap_kobo: int = 100_000 * NAIRA
    daily_cap_kobo: int = 200_000 * NAIRA
    risk_timezone: str = "Africa/Lagos"  # the daily cap counts Lagos calendar days

    # --- rate limits ---
    claim_attempts_per_minute: int = 5
    claim_lock_wrong_tries: int = 5
    claim_lock_seconds: int = 300
    approve_attempts_per_minute: int = 10
    login_attempts_per_minute: int = 10

    # --- demo console: exists only when DEMO_MODE is true and a demo token is sent ---
    demo_mode: bool = False
    demo_token: str = ""

    # --- Phase 2 and 3 flags: all off ---
    feature_sse: bool = False
    feature_renew: bool = False
    feature_voice: bool = False
    feature_card_guard: bool = False
    feature_failure_injection: bool = False
    feature_phone_call: bool = False

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// driver")
        return v

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.origin.split(",") if o.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required values come from the environment
