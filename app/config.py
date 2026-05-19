from functools import lru_cache

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class XUIServerConfig(BaseModel):
    api_url: str
    public_base_url: str
    username: str
    password: str
    inbound_id: int
    flow: str = ""
    sub_template: str = "{public_base_url}/sub/{sub_id}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    APP_BASE_URL: str

    YOOKASSA_WEBHOOK_PATH: str = "/yookassa/webhook"
    YOOKASSA_RETURN_URL: str
    YOOKASSA_SHOP_ID: str
    YOOKASSA_SECRET_KEY: str
    YOOKASSA_VAT_CODE: int = 1
    YOOKASSA_TAX_SYSTEM_CODE: int = 1

    SUPPORT_USERNAME: str = "@support"
    ADMIN_IDS: list[int] = []

    XUI_FINLAND_API_URL: str
    XUI_FINLAND_PUBLIC_BASE_URL: str
    XUI_FINLAND_USERNAME: str
    XUI_FINLAND_PASSWORD: str
    XUI_FINLAND_INBOUND_ID: int
    XUI_FINLAND_FLOW: str = ""
    XUI_FINLAND_SUB_TEMPLATE: str = "{public_base_url}/sub/{sub_id}"

    XUI_BYPASS_API_URL: str
    XUI_BYPASS_PUBLIC_BASE_URL: str
    XUI_BYPASS_USERNAME: str
    XUI_BYPASS_PASSWORD: str
    XUI_BYPASS_INBOUND_ID: int
    XUI_BYPASS_FLOW: str = ""
    XUI_BYPASS_SUB_TEMPLATE: str = "{public_base_url}/sub/{sub_id}"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, value):
        if value in (None, "", []):
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        return [int(part.strip()) for part in str(value).split(",") if part.strip()]

    @property
    def finland_server(self) -> XUIServerConfig:
        return XUIServerConfig(
            api_url=self.XUI_FINLAND_API_URL,
            public_base_url=self.XUI_FINLAND_PUBLIC_BASE_URL,
            username=self.XUI_FINLAND_USERNAME,
            password=self.XUI_FINLAND_PASSWORD,
            inbound_id=self.XUI_FINLAND_INBOUND_ID,
            flow=self.XUI_FINLAND_FLOW,
            sub_template=self.XUI_FINLAND_SUB_TEMPLATE,
        )

    @property
    def bypass_server(self) -> XUIServerConfig:
        return XUIServerConfig(
            api_url=self.XUI_BYPASS_API_URL,
            public_base_url=self.XUI_BYPASS_PUBLIC_BASE_URL,
            username=self.XUI_BYPASS_USERNAME,
            password=self.XUI_BYPASS_PASSWORD,
            inbound_id=self.XUI_BYPASS_INBOUND_ID,
            flow=self.XUI_BYPASS_FLOW,
            sub_template=self.XUI_BYPASS_SUB_TEMPLATE,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()