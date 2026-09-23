import base64
import hashlib
import hmac

import requests
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError, Timeout
from websockets.exceptions import InvalidHandshake, InvalidStatus, WebSocketException

TRANSIENT_STATUS_CODES = {408, 429, 502, 503, 504}
def is_transient_post_error(exc: BaseException):
    if isinstance(exc,requests.exceptions.HTTPError):
        return exc.response is not None and exc.response.status_code in TRANSIENT_STATUS_CODES
    return isinstance(exc,(ConnectionError,Timeout))

def verify_meta_signature(raw_body:bytes,signature:str | None,app_secret:str):
    if not signature:
        return False

    elements = signature.split("sha256=")
    if len(elements) != 2:
        return False

    expected_signature = elements[1]

    mac = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    )
    generated_signature = mac.hexdigest()

    return hmac.compare_digest(generated_signature,expected_signature)



def extract_email_body(payload) -> str | None:
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
            found = extract_email_body(part)
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


TRANSIENT_HANDSHAKE_STATUSES: set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests (Rate limit)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

def is_transient_websocket_error(exc:BaseException):
    if isinstance(exc,(OSError,ConnectionRefusedError,ConnectionResetError,TimeoutError)):
        return True
    if isinstance(exc,InvalidStatus):
        return exc.response.status_code in TRANSIENT_HANDSHAKE_STATUSES
    if isinstance(exc,(InvalidHandshake)):
        return True
    if isinstance(exc, WebSocketException):
        exc_name = type(exc).__name__
        return any(k in exc_name for k in ("Timeout", "Reset", "Aborted"))
    return False