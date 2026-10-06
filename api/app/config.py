from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DB_USER: str = "enchentes"
    DB_PASSWORD: str = "enchentes"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "enchentes"

    DB_POOL_MIN_SIZE: int = 4
    DB_POOL_MAX_SIZE: int = 20

    API_KEYS: str = ""

    @property
    def chaves_validas(self) -> list[str]:
        return [c.strip() for c in self.API_KEYS.split(",") if c.strip()]

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
