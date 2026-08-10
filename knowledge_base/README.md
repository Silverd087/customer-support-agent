# Knowledge base — test set

Fictional company (Lumen Home, smart home devices + Lumen+ subscription) built for testing the RAG pipeline. Five docs: `faq.md`, `shipping_and_returns.md`, `billing_and_subscriptions.md`, `troubleshooting_guide.md`, `account_and_security.md`.

Deliberately **not** covered here: live order status, account-specific data (a customer's actual plan, order history, ticket history). Those live in the database and should be answered by the `get_order_status`-style tool from Sprint 4, not RAG — the gap is intentional, so you can test that the agent routes correctly instead of hallucinating an answer from these docs.

## Suggested test questions (grounded — should answer correctly)

- What Wi-Fi frequency do Lumen devices need?
- How long is the return window, and does the item need original packaging?
- If I cancel Lumen+, when do I stop being charged, and what happens to my recordings?
- My thermostat's temperature reading looks wrong — what should I check first?
- How does 2-factor authentication recovery work if I lose my phone?
- Can I get a partial refund for the unused part of a billing cycle if I cancel mid-month?
- Is water damage covered under warranty?

## Suggested out-of-scope questions (should say "I don't know" / escalate, not guess)

- What's the status of my order #48213? *(this is the DB-tool case, not RAG — good for testing routing once Sprint 4 is done)*
- Do you ship to Australia? *(docs only cover US, Canada, UK — a good hallucination trap)*
- Can I pay by cryptocurrency? *(explicitly listed as unsupported — checks the agent reads negatives correctly, not just keyword-matches "payment")*
- My camera feed was accessed by someone else, what do I do? *(should escalate to a human per the Suspicious Activity section, not troubleshoot automatically)*

## Adding your own real documents later

Once you're ready to move off this test set, drop your real FAQs/policies in here (same folder, any mix of `.md`/`.pdf`/`.txt` depending on what your ingestion script in Sprint 2 supports) and re-run ingestion. Consider keeping this test set around in a separate branch or folder — it's useful for regression-testing the pipeline after prompt/chunking changes even after you switch to real content.
