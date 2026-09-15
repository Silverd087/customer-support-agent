
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from logger import logger
from tenacity import retry,stop_after_attempt,wait_exponential,retry_if_exception_type
from google.auth.exceptions import RefreshError
from database.session import get_db
from config import settings
from database.models.oauth_credentials import OauthCredentials
from sqlalchemy import update,select
from sqlalchemy import create_engine
write_url = f"postgresql+psycopg2://{settings.write_role_user}:{settings.write_role_password}@{settings.db_host}/{settings.db_name}"
write_engine = create_engine(url=write_url)


def get_gmail():
    creds = None
    with get_db(write_engine) as db:
        stmt = select(OauthCredentials).where(OauthCredentials.provider == "GOOGLE")
        creds = db.execute(stmt).scalar_one_or_none().token_json
        logger.info("gmail_token_fetched")
        if not creds:
            logger.info("gmail_token_not_found")
            raise Exception("token not found")
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        logger.info("gmail_token_refreshed")
        with get_db(write_engine) as db:
            stmt = update(OauthCredentials).where(OauthCredentials.provider == "GOOGLE").values(token_json = creds)
            db.execute(stmt)
            db.commit()
    return creds

def get_gmail_headers():
    creds = get_gmail()
    return {"Authorization": f"Bearer {creds.token}"}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10),retry=retry_if_exception_type(RefreshError))
def get_gmail_service():
    """Same gmail_token.json the specialist uses — sending only needs
    gmail.compose, which is already granted, so no separate credential
    is required. See the write-up on why this can't be scope-restricted
    further: gmail.compose bundles draft creation and send together."""
    creds = get_gmail()
    return build("gmail", "v1", credentials=creds)