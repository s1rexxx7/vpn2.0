from functools import lru_cache
from pydantic import BaseModel, Field
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

    XUI_GERMANY_API_URL: str
    XUI_GERMANY_PUBLIC_BASE_URL: str
    XUI_GERMANY_USERNAME: str
    XUI_GERMANY_PASSWORD: str
    XUI_GERMANY_INBOUND_ID: int
    XUI_GERMANY_FLOW: str = ""
    XUI_GERMANY_SUB_TEMPLATE: str = "{public_base_url}/sub/{sub_id}"

    XUI_BYPASS_API_URL: str
    XUI_BYPASS_PUBLIC_BASE_URL: str
    XUI_BYPASS_USERNAME: str
    XUI_BYPASS_PASSWORD: str
    XUI_BYPASS_INBOUND_ID: int
    XUI_BYPASS_FLOW: str = ""
    XUI_BYPASS_SUB_TEMPLATE: str = "{public_base_url}/sub/{sub_id}"

    @property
    def germany_server(self) -> XUIServerConfig:
        return XUIServerConfig(
            api_url=self.XUI_GERMANY_API_URL,
            public_base_url=self.XUI_GERMANY_PUBLIC_BASE_URL,
            username=self.XUI_GERMANY_USERNAME,
            password=self.XUI_GERMANY_PASSWORD,
            inbound_id=self.XUI_GERMANY_INBOUND_ID,
            flow=self.XUI_GERMANY_FLOW,
            sub_template=self.XUI_GERMANY_SUB_TEMPLATE,
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