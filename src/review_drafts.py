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
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import database.models  # noqa: F401
from database.engines import review_engine
from database.models.pending_email_send import PendingEmailSend, Status
from gmail_credentials import get_gmail_service

SessionLocal = sessionmaker(bind=review_engine, expire_on_commit=False)



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
                draft.sent_at = datetime.now(UTC)
                draft.reviewed_by = reviewer
                draft.reviewed_at = datetime.now(UTC)
                db.commit()
                print("Sent and marked 'sent'.")

            elif choice == "r":
                draft.status = Status.REJECTED
                draft.reviewed_by = reviewer
                draft.reviewed_at = datetime.now(UTC)
                db.commit()
                print("Marked 'rejected' — draft left unsent in Gmail.")

            else:
                print("Unrecognized choice, skipping.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
