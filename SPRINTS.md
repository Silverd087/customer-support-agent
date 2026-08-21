# Sprint Plan: Customer Support Agent

Companion to `customer_support_agent_guide.md`. Work top to bottom — each sprint depends on the one before it. You write the code; bring it to me at the end of each sprint (or anytime you're stuck) and I'll review against the guide.

Check items off as you go. "Done when" is the bar for moving to the next sprint — don't skip it even if the code "basically works."

**Architecture change as of Sprint 3:** the fixed `classify_intent → retrieve_context → generate_response` pipeline from Sprint 2 is being restructured into an **orchestrator + specialist agents** design (see guide §1–§9) — an orchestrator that calls specialist agents (RAG, DB, Gmail) as tools, instead of one linear path. Your Sprint 2 work isn't wasted: `retrieve_context` and `generate_response`'s logic become the RAG specialist's `search_knowledge_base` tool and system prompt in Sprint 3. `classify_intent` as a hard gate goes away — routing is now the orchestrator's job via tool selection.

---

## Sprint 0 — Setup ✅

- [x] Create project structure (`src/`, `knowledge_base/`, `tests/`, `.env`, `.gitignore`)
- [x] Set up a virtual environment and `requirements.txt`: `langgraph`, `langchain`, `langchain-openai`, `langchain-chroma`, `langchain-text-splitters`
- [x] Get API keys (LLM provider, at minimum) into `.env`, confirm `.env` is in `.gitignore`
- [x] Drop 3–5 real support documents into `knowledge_base/`

**Done when:** `pip install -r requirements.txt` runs clean and you can load your API key from `.env` in a throwaway script.

---

## Sprint 1 — Bare graph plumbing (no intelligence yet) ✅

- [x] Define state (TypedDict)
- [x] Build a single-node graph where the node just echoes the input back
- [x] Compile it, invoke it from a CLI loop, confirm state flows through correctly

**Done when:** you can type a message in a terminal loop and get a canned response back through an actual LangGraph `app.invoke()` call.

---

## Sprint 2 — Text + RAG core (fixed pipeline) ✅

- [x] Write the ingestion script: load `knowledge_base/`, chunk, embed, store in Chroma
- [x] Build `classify_intent` node (real LLM call)
- [x] Build `retrieve_context` node (real vector search)
- [x] Build `generate_response` node, grounded in retrieved chunks, with an explicit "say you don't know" instruction
- [x] Wire `classify_intent → retrieve_context → generate_response` in the graph
- [x] Test via CLI with at least 10 real questions from your docs, and 2–3 questions your docs *don't* cover

**Done when:** the agent answers your test questions correctly and grounded, and doesn't hallucinate on the out-of-scope ones. This code becomes the basis for the RAG specialist in Sprint 3, not throwaway work.

---

## Sprint 2b — RAG quality & production habits

- [x] Tag each chunk with a `category` metadata field at ingest time (map source doc → billing/technical/account/other) — kept as a soft signal / logging field, not a hard retrieval filter (see note below)
- [ ] Turn `knowledge_base/README.md`'s test questions into a retrieval-quality eval script — checks whether the right doc/chunk comes back per question, not the full LLM answer yet
- [ ] Add logging per query: question, retrieved chunks (doc + similarity score), final answer
- [ ] Use `similarity_search_with_score` to get a distance for the best-matching chunk, as an early confidence signal — feeds into the RAG specialist's grounding/escalation behavior (Sprint 3, Sprint 6)
- [ ] Centralize config (`chunk_size`, `chunk_overlap`, `k`, `collection_name`, model names) into one place instead of duplicated across files

**Dropped from the original plan:** hard-filtering retrieval by classified intent category. Since the orchestrator architecture removes `classify_intent` as a gate, there's no hard filter to build — a mismatch between how a chunk got categorized at ingest and how a live question gets classified used to risk silently excluding the right chunk (the FAQ doc was the clearest case, since it mixes topics). Category metadata is still worth keeping on chunks for logging/analytics, just not as something that can exclude a correct answer.

**Deliberately not doing yet:** hybrid search (BM25 + vector) and reranking — nothing to observe them improving against a 5-doc test knowledge base yet.

**Done when:** the eval script runs and reports pass/fail per question, every query produces a retrieval log line, and there's no duplicated config across files.

---

## Sprint 3 — RAG specialist

Turn Sprint 2's retrieval + generation logic into a self-contained specialist agent, tested on its own — no orchestrator yet.

- [ ] Wrap retrieval as a tool: `search_knowledge_base(query: str) -> str`, using `similarity_search_with_score` (drop the category filter per Sprint 2b)
- [ ] Build the RAG specialist's own small graph: an `agent` node (LLM bound to `search_knowledge_base`) + `ToolNode` + `tools_condition` loop (see guide §2 skeleton)
- [ ] Move the grounding instruction ("answer only from what the tool returns, say when you don't know, never invent policy/price/timeline details") into the specialist's own system prompt
- [ ] Wrap the compiled specialist in `@tool def rag_specialist(question: str) -> str`
- [ ] Test by invoking `rag_agent.invoke(...)` directly (not through an orchestrator) against your Sprint 2 test questions, including the out-of-scope ones

**Done when:** `rag_specialist` alone reproduces (or beats) Sprint 2's answer quality, called as a standalone function — no orchestrator involved yet.

---

## Sprint 4 — Orchestrator + RAG specialist

- [ ] Build the orchestrator: an `agent` node (LLM bound to `[rag_specialist]`) + `ToolNode` + `tools_condition` loop, same shape as the specialist itself (guide §2)
- [ ] Add a `MemorySaver` checkpointer to the **orchestrator's** compiled graph, with a `thread_id` per conversation — specialists don't get their own checkpointer, they're invoked fresh each call
- [ ] Test via CLI: does the orchestrator correctly call `rag_specialist` for policy/FAQ questions?
- [ ] Test multi-turn: a follow-up question that depends on earlier context in the conversation
- [ ] Test that the orchestrator doesn't answer policy questions from its own memory without calling `rag_specialist` first (this is enforced by prompt instruction, not architecture — actually check it holds)

**Done when:** a 3+ turn conversation keeps context correctly, and every policy-grounded answer visibly went through `rag_specialist` (check your logs from Sprint 2b).

---

## Sprint 5 — DB specialist

- [ ] Stand up Postgres locally (or Docker), create a sample `orders`/`pending_refunds` schema with fake data
- [ ] Create a **read-only** DB role for `get_order_status`, and a separate, narrowly-scoped role for `create_refund_request` that can only insert into `pending_refunds` — never able to touch `orders`/`payments` directly
- [ ] Write `get_order_status(order_id, customer_email)` as an `@tool`, scoped to require both parameters
- [ ] Write `create_refund_request(order_id, customer_email, reason)` as an `@tool` — creates a pending record only, **never** issues a real refund
- [ ] Build the DB specialist the same shape as the RAG specialist (agent + ToolNode + tools_condition, both tools bound), wrap as `@tool def db_specialist(...)`
- [ ] Add `db_specialist` to the orchestrator's tool list
- [ ] Test the **compound case**: a refund request that requires the orchestrator to call both `db_specialist` (check the order) and `rag_specialist` (check refund policy) before deciding
- [ ] Adversarial test: try to get the agent to leak another "customer's" order data by manipulating the prompt — confirm the scoping (both params required) holds

**Done when:** the compound refund scenario correctly calls both specialists in a sensible order, and the adversarial test fails to leak data.

---

## Sprint 6 — Escalation as a tool

- [ ] Write `escalate_to_human(summary, reason) -> str` as an `@tool` (creates a ticket/notification — your choice of mechanism)
- [ ] Add `escalate_to_human` to the orchestrator's tool list
- [ ] Update the orchestrator's system prompt with explicit escalation triggers: RAG specialist reports low/no relevant info, customer explicitly asks for a human, anything security/safety-related
- [ ] Have `search_knowledge_base` surface a confidence signal in its return text (using the Sprint 2b distance score) so `rag_specialist` can honestly report "I don't have good information on this" back to the orchestrator
- [ ] Test: an out-of-scope question triggers escalation instead of a guessed answer
- [ ] Test: "let me talk to a person" triggers escalation immediately, no argument
- [ ] Test: a low-confidence RAG result triggers escalation rather than a low-confidence answer being returned to the customer

**Done when:** all three escalation triggers fire reliably across multiple phrasings, not just the exact test wording.

---

## Sprint 7 — Email channel (Gmail specialist)

**Design update:** unlike the original plan, this now includes a real send capability — gated behind human approval instead of banned outright. The send tool exists on the Gmail MCP connection, but it is never bound to the Gmail specialist's own conversational LLM. It's only ever invoked by a separate, human-driven approval process outside the LangGraph graph entirely. `pending_email_sends` (in `schema.sql`/`roles.sql`) is the mechanism that enforces this split — mirrors the `pending_refunds` pattern (agent creates a pending record, never executes the consequential action directly).

- [x] Install `langchain-mcp-adapters`; pick a Gmail MCP server (or write a minimal custom one exposing only the tools you need) and get it connected via `MultiServerMCPClient` — using Google's official `gmailmcp.googleapis.com` (Developer Preview)
- [x] Confirm you can list the server's available tools before binding anything — check what `search_threads`/`get_thread`/`create_draft`/send actually look like on this specific server — confirmed no send tool exists on this server at all
- [x] Build `database/pending_email_send.py`, matching the `pending_email_sends` table — same shape as `pending_refund.py`
- [x] Build the Gmail specialist the same shape as the others (agent node + `ToolNode` + `tools_condition` loop), bound to **only** `search_threads`, `get_thread`, `create_draft` — the send tool must not be in this list, even though it's available on the same MCP connection
- [x] Implement `create_draft`: calls the MCP server's draft-creation tool, then inserts a `pending_email_sends` row (`status='pending_review'`) using `agent_refund_writer`'s connection — including `replyToMessageId` support for threaded replies
- [x] Wrap as `gmail_specialist` `@tool` with a docstring the orchestrator can act on (same pattern as `db_specialist`), add to the orchestrator's tool list, update the orchestrator's system prompt to mention it
- [x] Build the human approval script (separate from the LangGraph graph, connects as `human_reviewer`): lists `pending_review` rows, human approves or rejects; on approval, calls Gmail's send API directly using the stored `gmail_draft_id`, updates `status`/`sent_at`; on rejection, updates `status`/`reviewed_by`/`reviewed_at` and leaves the draft unsent — `src/review_drafts.py`
- [ ] Build the channel adapter: pull new support emails, invoke the orchestrator with the email thread id as `thread_id`
- [ ] Test end-to-end: a real (or test) email thread produces a draft, a correct `pending_email_sends` row, and the draft is visible in Gmail
- [ ] Test the approval path both ways: approving actually sends; rejecting leaves it unsent
- [ ] Adversarial test: try to get the Gmail specialist to send directly via prompt manipulation ("just send it now", "skip the review") — confirm it structurally can't, because the send tool was never bound to its LLM in the first place

**Done when:** a real incoming email produces a correctly-drafted reply and a `pending_email_sends` row, the approval script is the only path that can make it actually send, and the adversarial test fails to bypass that — not because the model refused, but because the tool isn't there to call.

---

## Sprint 8 — WhatsApp channel

- [ ] Create a Meta developer app + test WhatsApp number, get the access token and phone number id
- [ ] Build the FastAPI webhook: `GET /webhook` (verification challenge) and `POST /webhook` (incoming messages)
- [ ] Verify the `X-Hub-Signature-256` header on incoming requests
- [ ] Build `send_whatsapp_message`, using the customer's phone number as `thread_id`
- [ ] Test a real round-trip conversation from your own phone, including at least one compound (DB + RAG) question

**Done when:** you can message your test WhatsApp number and hold a multi-turn conversation with the full orchestrator (not just RAG).

---

## Sprint 9 — Voice channel

- [ ] Integrate Wispr Flow for speech-to-text (voice in)
- [ ] Integrate ElevenLabs `text_to_speech.convert` (voice out)
- [ ] Wire an adapter that takes audio in, transcribes, invokes the orchestrator, synthesizes the reply
- [ ] Test a full voice round-trip

**Done when:** you can speak a question and hear a correct, grounded spoken answer.

---

## Sprint 9b — Reflection pattern for the RAG specialist (optional enhancement)

Do this only once Sprints 3–9 are solid — it's an upgrade to one already-working specialist, not a prerequisite for anything else.

- [ ] Add a `critique` node inside the RAG specialist's subgraph: checks the draft answer against what `search_knowledge_base` actually returned
- [ ] Loop back to the specialist's `agent` node for a revision if the critique finds unsupported claims, capped at ~2 retries
- [ ] Fall through to returning the draft (or signaling low confidence) if it still isn't approved after the retry cap
- [ ] Re-run your eval set and compare hallucination rate before/after — this is the way to tell if the extra complexity is actually earning its keep

**Done when:** you can point to specific eval cases where the reflection loop caught and fixed an unsupported claim.

---

## Sprint 10 — Production hardening (app-level)

- [ ] Swap `MemorySaver` for `PostgresSaver` on the orchestrator's checkpointer
- [ ] Add structured logging (or LangSmith tracing) covering: which specialists the orchestrator called and in what order, each specialist's own tool calls, and the final response — all tagged with `thread_id`
- [ ] Add retries + timeouts (e.g. `tenacity`) on every external call: LLM, embeddings, DB, ElevenLabs, Wispr Flow, WhatsApp, Gmail — remember a single turn may now chain several LLM calls across specialists
- [ ] Add per-customer/thread rate limiting
- [ ] Move all secrets to env vars / a secrets manager; double-check nothing is hardcoded or committed
- [ ] Add idempotency: dedupe on provider message id so retried webhooks don't double-process
- [ ] Add a lightweight `/health` endpoint (used by the Docker healthcheck and k8s probes in Sprint 10b)

**Done when:** you can kill and restart the process mid-conversation and it resumes correctly, and a duplicate webhook delivery doesn't produce a duplicate reply.

---

## Sprint 10b — Deployment infrastructure: Docker, CI/CD, Kubernetes, ArgoCD

Do this in order — each step should work manually before you automate it. See guide §13 for the full manifests/pipeline.

- [ ] Write the multi-stage `Dockerfile`; `docker build` and `docker run` it locally, confirm `/health` responds
- [ ] Set up CI (GitHub Actions): lint → test → run the Sprint 11 eval set → build & push the image to a registry
- [ ] Write the Kubernetes `Deployment`/`Service`/`HorizontalPodAutoscaler` manifests; `kubectl apply` them manually to a test cluster (e.g. local `kind`/`minikube`) and confirm the pod goes healthy and serves traffic
- [ ] Get readiness vs. liveness probes actually differentiated
- [ ] Create a separate GitOps config repo holding just the `k8s/` manifests
- [ ] Extend CI with a `bump-manifest` job that updates the image tag in the config repo on merge to main
- [ ] Install ArgoCD on the cluster, apply the `Application` manifest pointing at your config repo, confirm it auto-syncs
- [ ] Test the GitOps loop end to end: merge a code change → CI builds/pushes/bumps manifest → ArgoCD deploys automatically, no manual `kubectl`
- [ ] Test `selfHeal`: manually `kubectl edit` a deployed resource and confirm ArgoCD reverts it back to match Git

**Done when:** a merge to `main` results in the new version running in the cluster with zero manual `kubectl` commands, and a manual cluster edit gets auto-reverted by ArgoCD.

---

## Sprint 11 — Evaluation & polish

- [ ] Build a test set: 20–30 question/expected-answer pairs covering RAG, DB, compound (RAG+DB) requests, and escalation cases
- [ ] Write a script that runs the test set through the full orchestrator and scores/flags mismatches — check not just the final answer but *which specialists got called*, so a wrong answer can be traced to routing vs. a specialist's own mistake
- [ ] Iterate on prompts/chunking/tool schemas based on failures
- [ ] Full review pass across all four channels

**Done when:** your eval set passes consistently, and you (or I, reviewing) can't find an obvious gap across channels or specialists.

Note: Sprint 10b's CI step runs this eval script, so build a minimal version of it early and flesh it out here.

---

# Phase 2: Beyond a learning project — SaaS + portfolio

See guide §15–§20. Do Sprint 12 first — it's a foundational retrofit, much cheaper now than after building further on single-tenant assumptions.

## Sprint 12 — Multi-tenancy retrofit

- [ ] Update your models per `sql/schema.sql`: `tenants` table, `tenant_id` on every table, `orders` split into a surrogate `id` + tenant-scoped `order_number`
- [ ] Apply the RLS policies in `sql/roles.sql`; confirm `SET app.current_tenant_id` actually blocks cross-tenant reads even with the application-level filter temporarily removed
- [ ] Namespace Chroma collections per tenant (`tenant_{tenant_id}_kb`), re-ingest `knowledge_base/` under a tenant-scoped collection
- [ ] Template the orchestrator's system prompt to pull business name/persona from tenant config instead of the hardcoded "Lumen Home"
- [ ] Build a `build_orchestrator(tenant_id)` factory + simple cache (guide §15), replacing the module-level singleton orchestrator
- [ ] Test isolation explicitly using `sql/seed.sql`'s two tenants: confirm tenant 2 can never retrieve tenant 1's order or knowledge-base data, including via a deliberately manipulated prompt trying to reference another tenant

**Done when:** two tenants' data provably never cross — verified at both the application level and by confirming RLS blocks it independently.

---

## Sprint 13 — Real customer authentication

- [ ] Design step-up verification for `create_refund_request`: OTP to the email/phone on file, or order number + last-4-digits match, before the tool executes
- [ ] Wire channel-level identity signals for reads: WhatsApp phone number matched against the customer's registered phone; web widget requires login and passes a verified `customer_id` directly into the orchestrator invocation, not extracted from conversation text
- [ ] Test: attempt to fetch another customer's order using a guessed email — confirm it fails
- [ ] Test: attempt `create_refund_request` without completing step-up verification — confirm it's blocked

**Done when:** nothing with real consequences trusts free-text identity alone.

---

## Sprint 14 — Admin dashboard

- [ ] Doc upload flow that triggers tenant-scoped ingestion
- [ ] Analytics view: conversation volume, escalation rate, RAG hit rate (from Sprint 10's logging)
- [ ] `pending_refunds` review/approve/reject UI
- [ ] Tenant config UI: business name/persona feeding the templated system prompt

**Done when:** a business owner can onboard their own docs and act on a pending refund without touching the database directly.

---

## Sprint 15 — Human-agent handoff UI

- [ ] Live view of escalated conversations with full context
- [ ] A "paused for human" flag per `thread_id` that the orchestrator checks before responding
- [ ] Human replies appear in the same channel (WhatsApp/Gmail/chat) the customer is using

**Done when:** a human can take over an escalated conversation and the bot stays silent until handed back.

---

## Sprint 16 — Billing

- [ ] Stripe integration; `tenants.plan` tied to a subscription
- [ ] Webhook updates `tenants.status` on payment success/failure
- [ ] Usage metering per tenant (conversations/messages) if pricing is usage-based

**Done when:** a new tenant can sign up, pay, and reach `active` status automatically, no manual step.

---

## Sprint 17 — Portfolio polish

- [ ] Deploy live and reachable, using Sprint 10b's K8s/ArgoCD setup
- [ ] Add a web chat widget channel — the easiest for a stranger to try, no WhatsApp Business setup required
- [ ] Architecture write-up / README overhaul (the orchestrator/specialist/reflection pattern is genuinely differentiated material worth explaining well)
- [ ] Stub a data retention/deletion policy for tenant data, mirroring `account_and_security.md`'s own 30-day pattern applied to the SaaS itself

**Done when:** a stranger can try the live demo, and you have a written explanation of the architecture to point them to.

---

## How we'll work through this

Bring me code at the end of each sprint's tasks — or sooner if you get stuck on a specific piece. I'll check it against `customer_support_agent_guide.md` and flag bugs, security gaps (especially in Sprints 5, 7, 10, 12, 13), and infra issues (Sprint 10b). Sprint 2/2b are done — Sprint 3 (RAG specialist) is next; Phase 2 starts once Sprint 11 is done.
