from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # JWT Auth Config
    jwt_secret: str = Field(default="production_super_secret_key_change_me_in_env")
    jwt_algorithm: str = Field(default="HS256")
    
    # PostgreSQL Configuration
    # Default connection: postgresql://username:password@localhost:5432/database_name
    database_url: str = Field(default="postgresql+pg8000://postgres:postgres@localhost:5432/hnx_quantum")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Silently ignore unknown .env variables (e.g. legacy keys)

settings = Settings()
