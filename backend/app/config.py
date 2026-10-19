from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SME Finance Assistant"
    database_url: str = "sqlite:///./finance.db"
    secret_key: str = "change-me-in-production"
    field_encryption_key: str = ""  # Fernet key; derived from secret_key when empty
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False  # set True behind HTTPS
    cors_origins: str = "http://localhost:3000"

    # Free LLM providers, tried in this order. Unconfigured ones are skipped.
    llm_providers: str = "gemini,groq,ollama"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_enabled: bool = False
    llm_timeout_seconds: float = 15.0

    agent_max_steps: int = 5

    tesseract_cmd: str = ""  # full path to tesseract.exe when it is not on PATH
    tessdata_prefix: str = ""  # folder holding eng.traineddata, if not next to the program

    # Reminder delivery. A channel with no credentials is "not configured": the owner sends the text themselves.
    brevo_api_key: str = ""  # email, https://www.brevo.com
    brevo_sender_email: str = ""  # a sender verified in Brevo
    brevo_sender_name: str = "CashPilot"
    # Mailjet (email over HTTPS, free plan: 200 a day). The sender must be a verified address.
    mailjet_api_key: str = ""
    mailjet_secret_key: str = ""
    mailjet_sender_email: str = ""
    # Plain SMTP: any mailbox works, including a free Gmail one (smtp.gmail.com, port 587, an app password).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # defaults to smtp_user
    # Which WhatsApp provider to use: auto (Meta if its keys are set, else Twilio), meta, or twilio.
    whatsapp_provider: str = "auto"
    whatsapp_token: str = ""  # Meta WhatsApp Cloud API access token
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = ""  # an approved template; lets a reminder reach customers who have not messaged you
    whatsapp_template_lang: str = "en_US"
    twilio_account_sid: str = ""  # WhatsApp through Twilio, https://www.twilio.com
    twilio_auth_token: str = ""
    # The WhatsApp sender: the sandbox number "whatsapp:+14155238886", or your approved sender.
    twilio_whatsapp_from: str = ""

    # Stripe (use test keys until the business is verified). BILLING_MODE=stripe turns checkout on.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""  # the recurring price of the Pro plan
    app_url: str = "http://localhost:3000"  # where Stripe sends people back to

    # Plaid bank connection. Start with PLAID_ENV=sandbox (fake banks, no real data).
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"  # sandbox | production

    billing_mode: str = "demo"  # demo: plan changes take no payment. Anything else needs a payment provider.
    scheduler_enabled: bool = True  # run the daily job inside the app
    daily_job_hour: int = 7
    alerts_log_path: str = "alerts.log"

    @field_validator("whatsapp_token", "whatsapp_phone_number_id", "twilio_account_sid", "twilio_auth_token",
                     "brevo_api_key", "mailjet_api_key", "mailjet_secret_key", "smtp_password", "stripe_secret_key",
                     "plaid_secret", mode="before")
    @classmethod
    def _clean_secret(cls, v):
        """A secret pasted into a dashboard often carries a space, a line break, quotes or a 'Bearer ' prefix."""
        if not isinstance(v, str):
            return v
        v = v.strip().strip("\"'").strip()
        if v.lower().startswith("bearer "):
            v = v[7:].strip()
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def provider_order(self) -> list[str]:
        return [p.strip().lower() for p in self.llm_providers.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
