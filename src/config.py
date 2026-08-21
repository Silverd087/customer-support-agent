from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    google_api_key:str
    anthropic_api_key:str
    write_role_user:str
    write_role_password:str
    read_role_user:str
    read_role_password:str
    human_reviewer_role_user:str
    human_reviewer_role_password:str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()