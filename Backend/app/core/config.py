from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL            : str
    TIENDANUBE_ACCESS_TOKEN : str
    TIENDANUBE_USER_ID      : str
    TIENDANUBE_CLIENT_SECRET: str
    TIENDANUBE_STORE_ID     : str
    EMAIL_PASSWORD          : str
    GOOGLE_API_KEY          : str
    API_V1_STR              : str = "/api/v1"

    API_SECRET_KEY          : str

    class Config:
        env_file = ".env"

settings = Settings()
