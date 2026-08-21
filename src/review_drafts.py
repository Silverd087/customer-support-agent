"""
Human approval CLI for pending Gmail drafts (Sprint 7).

Deliberately outside the LangGraph app entirely. Connects to Postgres as
`human_reviewer` — SELECT + UPDATE only on pending_email_sends, no INSERT —
so this process can approve/reject existing rows but can never create one.
Only this script (or the human running it) ever calls Gmail's actual send;
the Gmail specialist's LLM was never given a send tool to call in the first
place, on the MCP connection or otherwise.

Run: uv run python src/review_drafts.py
"""

import sys
from datetime import datetime, timezone

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from config import settings
from database.models.pending_email_send import PendingEmailSend, Status
from database.models.tenant import Tenant
from database.models.customer import Customer
from database.models.order_item import OrderItem
from database.models.order_return import OrderReturn
from database.models.order import Order
from database.models.payment import Payment
from database.models.pending_refund import PendingRefund
from database.models.product import Product
from database.models.warranty_claim import WarrantyClaim
from database.models.subscription import Subscription
from database.models.escalation import Escalation

review_url = f"postgresql+psycopg2://{settings.human_reviewer_role_user}:{settings.human_reviewer_role_password}@localhost/lumen_support"
review_engine = create_engine(url=review_url)
SessionLocal = sessionmaker(bind=review_engine, expire_on_commit=False)


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


def fetch_pending(db):
    stmt = (
        select(PendingEmailSend)
        .where(PendingEmailSend.status == Status.PENDING_REVIEW)
        .order_by(PendingEmailSend.created_at)
    )
    return db.scalars(stmt).all()


def send_draft(service, gmail_draft_id: str):
    # Gmail API convention: sending an existing draft only needs its id.
    return service.users().drafts().send(userId="me", body={"id": gmail_draft_id}).execute()


def print_draft(draft: PendingEmailSend) -> None:
    print("\n" + "-" * 60)
    print(f"id:              {draft.id}")
    print(f"customer_email:  {draft.customer_email}")
    print(f"subject:         {draft.subject}")
    print(f"gmail_draft_id:  {draft.gmail_draft_id}")
    print(f"thread_id:       {draft.thread_id}")
    print(f"created_at:      {draft.created_at}")
    print("-" * 60)


def main():
    reviewer = input("Reviewing as (name or email, stored on each row you act on): ").strip()
    if not reviewer:
        print("A reviewer name is required.")
        sys.exit(1)

    service = get_gmail_service()
    db = SessionLocal()

    try:
        pending = fetch_pending(db)
        if not pending:
            print("No drafts pending review.")
            return

        print(f"{len(pending)} draft(s) pending review.")

        for draft in pending:
            print_draft(draft)
            choice = input("[a]pprove and send / [r]eject / [s]kip / [q]uit: ").strip().lower()

            if choice == "q":
                break
            if choice == "s":
                continue

            if choice == "a":
                try:
                    send_draft(service, draft.gmail_draft_id)
                except Exception as e:
                    print(f"Failed to send via Gmail API — row left as pending_review: {e}")
                    continue
                draft.status = Status.SENT
                draft.sent_at = datetime.now(timezone.utc)
                draft.reviewed_by = reviewer
                draft.reviewed_at = datetime.now(timezone.utc)
                db.commit()
                print("Sent and marked 'sent'.")

            elif choice == "r":
                draft.status = Status.REJECTED
                draft.reviewed_by = reviewer
                draft.reviewed_at = datetime.now(timezone.utc)
                db.commit()
                print("Marked 'rejected' — draft left unsent in Gmail.")

            else:
                print("Unrecognized choice, skipping.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
