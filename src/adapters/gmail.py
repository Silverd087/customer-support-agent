
import asyncio
import time

from tenacity import retry, stop_after_attempt, wait_exponential

from adapters.utils import extract_email_body
from auth.gmail_credentials import get_gmail_service
from logger import logger
from orchestrator import handle_incoming


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
def mark_as_read_with_retry(service,id):
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
        messages.append(get_email_with_retry(service,msg['id']))
    return messages

def mark_as_read(id:str):
    service = get_gmail_service()
    mark_as_read_with_retry(service,id)


def run_gmail_poller(interval_seconds: int = 30):
    while True:
        unread_messages = poll_gmail_for_new_messages()
        if unread_messages:
            logger.info("gmail_poll_cycle", unread_count=len(unread_messages))
        for msg in unread_messages:
            try:
                payload = msg["payload"]
                body = extract_email_body(payload)
                if not body:
                    logger.warning("gmail_message_unreadable", message_id=msg["id"])
                    continue
                customer_email = next((header["value"] for header in payload["headers"] if header["name"].lower() == "from"), None)
                if not customer_email:
                    continue
                text = customer_email + '\n\n' + body
                asyncio.run(handle_incoming(text, msg["threadId"], "email"))
                logger.info("gmail_message_processed", message_id=msg["id"], thread_id=msg["threadId"])
            except Exception as e:
                logger.error("gmail_message_processing_failed", message_id=msg["id"], error=str(e))
                continue
            mark_as_read(msg["id"])
        time.sleep(interval_seconds)