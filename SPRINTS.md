# Sprint Plan: Customer Support Agent

Companion to `customer_support_agent_guide.md`. Work top to bottom — each sprint depends on the one before it. You write the code; bring it to me at the end of each sprint (or anytime you're stuck) and I'll review against the guide.

Check items off as you go. "Done when" is the bar for moving to the next sprint — don't skip it even if the code "basically works."

---

## Sprint 0 — Setup

- [ ] Create project structure (`src/`, `knowledge_base/`, `tests/`, `.env`, `.gitignore`)
- [ ] Set up a virtual environment and `requirements.txt`: `langgraph`, `langchain`, `langchain-openai`, `langchain-chroma`, `langchain-text-splitters`
- [ ] Get API keys (LLM provider, at minimum) into `.env`, confirm `.env` is in `.gitignore`
- [ ] Drop 3–5 real support documents into `knowledge_base/`

**Done when:** `pip install -r requirements.txt` runs clean and you can load your API key from `.env` in a throwaway script.

---

## Sprint 1 — Bare graph plumbing (no intelligence yet)

- [ ] Define `SupportState` (TypedDict)
- [ ] Build a single-node graph where the node just echoes the input back
- [ ] Compile it, invoke it from a CLI loop, confirm state flows through correctly

**Done when:** you can type a message in a terminal loop and get a canned response back through an actual LangGraph `app.invoke()` call. Purpose of this sprint: prove the plumbing works before adding any LLM calls, so later bugs are easier to isolate.

---

## Sprint 2 — Text + RAG core

- [ ] Write the ingestion script: load `knowledge_base/`, chunk, embed, store in Chroma
- [ ] Build `classify_intent` node (real LLM call)
- [ ] Build `retrieve_context` node (real vector search)
- [ ] Build `generate_response` node, grounded in retrieved chunks, with an explicit "say you don't know" instruction
- [ ] Wire `classify_intent → retrieve_context → generate_response` in the graph
- [ ] Test via CLI with at least 10 real questions from your docs, and 2–3 questions your docs *don't* cover (to check it admits it doesn't know instead of guessing)

**Done when:** the agent answers your test questions correctly and grounded, and doesn't hallucinate on the out-of-scope ones. This is the core of the whole project — don't rush it.

---

## Sprint 3 — Escalation + memory

- [ ] Add `confidence` and `needs_human` to state; have `generate_response` set confidence
- [ ] Add `route_after_generate` conditional edge → `human_handoff` node
- [ ] Add `MemorySaver` checkpointer with a `thread_id` per conversation
- [ ] Test a multi-turn conversation (ask a follow-up that depends on earlier context)
- [ ] Test a low-confidence case actually routes to `human_handoff`

**Done when:** a 3+ turn conversation keeps context correctly, and you can force an escalation and see it route correctly.

---

## Sprint 4 — Database tool

- [ ] Stand up Postgres locally (or Docker), create a sample `orders`/`tickets` schema with fake data
- [ ] Create a **read-only** DB role for the agent to connect as
- [ ] Write `get_order_status` (or similar) as an `@tool`, scoped to require the customer's own identifier as a parameter
- [ ] Wire `bind_tools`, `ToolNode`, `tools_condition` into the graph
- [ ] Test: ask an order-status question (should use the tool) and a policy question (should use RAG) — confirm the agent picks the right one each time
- [ ] Try to get the agent to leak another "customer's" data by manipulating the prompt — confirm the scoping holds

**Done when:** tool vs. RAG routing is reliable, and the adversarial test in the last item fails to leak data.

---

## Sprint 5 — Email channel (Gmail)

- [ ] Connect the Gmail MCP connector
- [ ] Build a loop/handler that pulls new support emails, maps them into `SupportState`, and invokes the graph with the email thread id as `thread_id`
- [ ] Build `format_for_channel_email` using `create_draft` — **never auto-send**
- [ ] Test end-to-end on a real (or test) email thread and manually review/send the draft

**Done when:** a real incoming email produces a correctly-drafted reply you'd be comfortable sending as-is.

---

## Sprint 6 — WhatsApp channel

- [ ] Create a Meta developer app + test WhatsApp number, get the access token and phone number id
- [ ] Build the FastAPI webhook: `GET /webhook` (verification challenge) and `POST /webhook` (incoming messages)
- [ ] Verify the `X-Hub-Signature-256` header on incoming requests
- [ ] Build `send_whatsapp_message`, using the customer's phone number as `thread_id`
- [ ] Test a real round-trip conversation from your own phone

**Done when:** you can message your test WhatsApp number and hold a multi-turn conversation with the agent.

---

## Sprint 7 — Voice channel

- [ ] Integrate Wispr Flow for speech-to-text (voice in)
- [ ] Integrate ElevenLabs `text_to_speech.convert` (voice out)
- [ ] Wire an adapter that takes audio in, transcribes, invokes the graph, synthesizes the reply
- [ ] Test a full voice round-trip

**Done when:** you can speak a question and hear a correct, grounded spoken answer.

---

## Sprint 8 — Production hardening (app-level)

- [ ] Swap `MemorySaver` for `PostgresSaver`
- [ ] Add structured logging (or LangSmith tracing) covering intent, retrieved chunks, tool calls, final response — all tagged with `thread_id`
- [ ] Add retries + timeouts (e.g. `tenacity`) on every external call: LLM, embeddings, DB, ElevenLabs, Wispr Flow, WhatsApp, Gmail
- [ ] Add per-customer/thread rate limiting
- [ ] Move all secrets to env vars / a secrets manager; double-check nothing is hardcoded or committed
- [ ] Add idempotency: dedupe on provider message id so retried webhooks don't double-process
- [ ] Add a lightweight `/health` endpoint (used by the Docker healthcheck and k8s probes in Sprint 8b)

**Done when:** you can kill and restart the process mid-conversation and it resumes correctly, and a duplicate webhook delivery doesn't produce a duplicate reply.

---

## Sprint 8b — Deployment infrastructure: Docker, CI/CD, Kubernetes, ArgoCD

Do this in order — each step should work manually before you automate it. See guide §11 for the full manifests/pipeline.

- [ ] Write the multi-stage `Dockerfile`; `docker build` and `docker run` it locally, confirm `/health` responds
- [ ] Set up CI (GitHub Actions): lint → test → run the Sprint 9 eval set → build & push the image to a registry
- [ ] Write the Kubernetes `Deployment`/`Service`/`HorizontalPodAutoscaler` manifests; `kubectl apply` them manually to a test cluster (e.g. local `kind`/`minikube`) and confirm the pod goes healthy and serves traffic
- [ ] Get readiness vs. liveness probes actually differentiated (readiness fails during startup/dependency warmup; liveness only fails if the process is truly stuck)
- [ ] Create a separate GitOps config repo holding just the `k8s/` manifests
- [ ] Extend CI with a `bump-manifest` job that updates the image tag in the config repo on merge to main
- [ ] Install ArgoCD on the cluster, apply the `Application` manifest pointing at your config repo, confirm it auto-syncs
- [ ] Test the GitOps loop end to end: merge a code change → CI builds/pushes/bumps manifest → ArgoCD deploys automatically, no manual `kubectl`
- [ ] Test `selfHeal`: manually `kubectl edit` a deployed resource and confirm ArgoCD reverts it back to match Git

**Done when:** a merge to `main` results in the new version running in the cluster with zero manual `kubectl` commands, and a manual cluster edit gets auto-reverted by ArgoCD.

---

## Sprint 9 — Evaluation & polish

- [ ] Build a test set: 20–30 question/expected-answer pairs covering RAG, DB tool, and escalation cases
- [ ] Write a script that runs the test set through the agent and scores/flags mismatches
- [ ] Iterate on prompts/chunking/tool schemas based on failures
- [ ] Full review pass across all four channels

**Done when:** your eval set passes consistently, and you (or I, reviewing) can't find an obvious gap across channels.

Note: Sprint 8b's CI step runs this eval script, so build a minimal version of it early and flesh it out here.

---

## How we'll work through this

Bring me code at the end of each sprint's tasks — or sooner if you get stuck on a specific piece. I'll check it against `customer_support_agent_guide.md` and flag bugs, security gaps (especially in Sprints 4, 6, 8), and infra issues (Sprint 8b — probe misconfiguration and overly-permissive ArgoCD sync policies are the common mistakes). Start with Sprint 0.
