import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings

ingestion_api_key = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key:str = Security(ingestion_api_key)):
    if not secrets.compare_digest(api_key,settings.ingestion_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")