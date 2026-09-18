import json

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

import database.models  # noqa: F401
from database.engines import write_engine
from database.models.oauth_credentials import OauthCredentials
from database.session import get_db

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',"https://www.googleapis.com/auth/gmail.compose"]
TOKEN_PATH = 'gmail_token.json'
CREDENTIALS_PATH = 'client_secret.json'

def get_credentials():
    creds = None
    with get_db(write_engine) as db:
        stmt = select(OauthCredentials).where(OauthCredentials.provider == "GOOGLE")
        creds_row = db.execute(stmt).scalar_one_or_none()
        creds = Credentials.from_authorized_user_info(creds_row.token_json) if creds_row else None
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with get_db(write_engine) as db:
            stmt = insert(OauthCredentials).values(
                provider="GOOGLE",token_json=json.loads(creds.to_json())
                ).on_conflict_do_update(
                    index_elements=["provider"],set_={"token_json":json.loads(creds.to_json())}
                    )
            db.execute(stmt)
            db.commit()
    return creds

if __name__ == "__main__":
    get_credentials()