from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import time
from agent import handle_incoming
from langchain.messages import HumanMessage
import base64
from bs4 import BeautifulSoup 
from tenacity import retry,wait_exponential,stop_after_attempt,retry_if_exception_type
from google.auth.exceptions import RefreshError



@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10),retry=retry_if_exception_type(RefreshError))
def get_gmail_service():
    """Same gmail_token.json the specialist uses — sending only needs
    gmail.compose, which is already granted, so no separate credential
    is required. See the write-up on why this can't be scope-restricted
    further: gmail.compose bundles draft creation and send together."""
    creds = Credentials.from_authorized_user_file("gmail_token.json")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("gmail_token.json", "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def list_emails_with_retry(service):
    return service.users().messages().list(
        userId="me",
        q='is:unread'
    ).execute()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def get_email_with_retry(service,id):
    return service.users().messages().get(
            userId='me', id=id
        ).execute()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def mark_as_read_with_retry(service):
    service.users().messages().modify(
        userId="me",
        id=id,
        body={'removeLabelIds': ['UNREAD']}
    ).execute()



def poll_gmail_for_new_messages():
    service = get_gmail_service()
    results = list_emails_with_retry(service)
    messages_ids = results.get('messages', [])
    messages = []
    for msg in messages_ids:
        message = get_email_with_retry(service,msg['id'])
    return messages

def mark_as_read(id:str):
    service = get_gmail_service()
    mark_as_read_with_retry(service)

def _extract_body(payload) -> str | None:
    """Walk a Gmail message payload for its text content.

    Real emails are usually multipart/alternative (a text/plain part and a
    text/html part carrying the same content) sometimes nested inside
    multipart/mixed if there are attachments — payload["body"]["data"] is
    only populated directly for simple, non-multipart messages. Prefers
    text/plain; falls back to a crude HTML-tag strip of text/html if no
    plain-text part exists anywhere in the tree.
    """
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data")
        return base64.urlsafe_b64decode(data).decode("utf-8") if data else None

    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            found = _extract_body(part)
            if found:
                return found
        return None

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data")
        if not data:
            return None
        html = base64.urlsafe_b64decode(data).decode("utf-8")
        # Crude fallback only — no bs4/html2text dependency added for this.
        # Reach for BeautifulSoup(html, "html.parser").get_text() instead
        # if this ever needs to handle real-world HTML reliably.
        return BeautifulSoup(html,"html.parser").get_text()

    return None


def run_gmail_poller(interval_seconds: int = 30):
    while True:
        unread_messages = poll_gmail_for_new_messages()
        for msg in unread_messages:
            try:
                payload = msg["payload"]
                body = _extract_body(payload)
                if not body:
                    print(f"No readable text/plain or text/html part found on {msg['id']}, skipping.")
                    continue
                customer_email = next((header["value"] for header in payload["headers"] if header["name"].lower() == "from"), None)
                text = customer_email + '\n\n' + body
                handle_incoming(text, msg["threadId"], "email")
            except Exception as e:
                print(f"Failed to process {msg["id"]}, left unread for retry: {e}")
                continue
            mark_as_read(msg["id"])
        time.sleep(interval_seconds)