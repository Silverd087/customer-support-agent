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
    verify_token:str
    app_secret:str
    whatsapp_access_token:str
    openai_api_key:str
    elevenlabs_api_key:str
    db_user:str
    db_password:str
    redis_url:str
    db_host:str
    db_name:str
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()