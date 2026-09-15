import os
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from database.session import get_db
from config import settings
from sqlalchemy import create_engine
from database.models.oauth_credentials import OauthCredentials
from sqlalchemy.dialects.postgresql import insert

write_url = f"postgresql+psycopg2://{settings.write_role_user}:{settings.write_role_password}@{settings.db_host}/{settings.db_name}"
write_engine = create_engine(url=write_url)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',"https://www.googleapis.com/auth/gmail.compose"]
TOKEN_PATH = 'gmail_token.json'
CREDENTIALS_PATH = 'client_secret.json'

def get_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                if os.path.exists(TOKEN_PATH):
                    os.remove(TOKEN_PATH)
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with get_db(write_engine) as db:
            stmt = insert(OauthCredentials).values(
                provider="GOOGLE",token_json=creds.to_json()
                ).on_conflict_do_update(
                    index_elements=["provider"],set_={"token_json":creds.to_json()}
                    )
            db.execute(stmt)
            db.commit()
    return creds

get_credentials()