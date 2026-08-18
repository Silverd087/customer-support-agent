# Customer Support Agent (Multi-Agent AI)

A multi-agent customer support assistant built with LangGraph: an **orchestrator** agent routes customer requests to **specialist** sub-agents (RAG, database, email) via tool-calling, instead of a fixed classify → retrieve → generate pipeline. Built as a hands-on project for learning agent architecture patterns — now being pushed toward a real, multi-tenant, production-grade system.

Full architecture write-up: [`customer_support_agent_guide.md`](./customer_support_agent_guide.md). Build plan and current progress: [`SPRINTS.md`](./SPRINTS.md).

## Status: in progress

**Built:**
- RAG specialist — a self-contained agent (its own LangGraph subgraph) that searches a Chroma vector store and grounds answers in retrieved policy/FAQ docs, refusing to guess when the knowledge base doesn't cover something
- Orchestrator agent that calls the RAG specialist via tool-calling, with a `MemorySaver` checkpointer for multi-turn conversation memory
- Retrieval-distance-based confidence signal (not a self-reported LLM confidence score) as the foundation for escalation logic
- Structured JSON logging for query/intent/retrieval tracing
- A multi-tenant PostgreSQL schema (`sql/`) — `tenants` table, `tenant_id` on every table, Row-Level Security policies for defense-in-depth isolation — designed ahead of wiring it into the app

**In progress / planned** (see `SPRINTS.md` for the full sequence):
- Database specialist (order lookups, refund requests — pending-approval only, never auto-executed)
- Escalation as a tool (`escalate_to_human`), triggered by low confidence, explicit request, or out-of-scope questions
- Gmail specialist (draft-only replies, human-reviewed)
- WhatsApp and voice (Wispr Flow / ElevenLabs) channels
- Multi-tenancy wired into the application layer, real customer authentication, admin dashboard, human-agent handoff UI
- Docker, CI/CD, Kubernetes, ArgoCD GitOps deployment

## Architecture

```
Channels (chat / voice / email / WhatsApp)
        │
        ▼
  Orchestrator agent ──tool call──▶ RAG specialist ──▶ Chroma vector store
        │                          DB specialist    ──▶ PostgreSQL (planned)
        │                          Gmail specialist  ──▶ Gmail (planned)
        ▼
  escalate_to_human (planned)
```

Each specialist is its own small agent (LLM + tools + its own tool-calling loop) wrapped as a single tool the orchestrator can call — so a specialist's internals (different model, added reflection/self-critique step, more tools) can change without touching the orchestrator. See the guide for the full rationale and code sketches.

## Tech stack

- **Orchestration:** LangGraph, LangChain
- **LLMs:** Google Gemini (`langchain-google-genai`), Anthropic Claude (`langchain-anthropic`) — used for different tasks (chunk categorization vs. main reasoning)
- **RAG:** Chroma (vector store), `BAAI/bge-m3` embeddings via `langchain-huggingface` (local, no per-call embedding cost)
- **Planned:** PostgreSQL (SQLAlchemy), Gmail MCP, Meta WhatsApp Cloud API, Wispr Flow, ElevenLabs

## Project structure

```
src/
  agent.py       # orchestrator + RAG specialist graphs
  ingest.py      # knowledge base ingestion (chunk, embed, categorize, store)
  config.py      # settings (pydantic-settings, .env-backed)
  logger.py      # structured JSON logging
  main.py
knowledge_base/  # source docs for RAG (test knowledge base: a fictional
                 # smart-home company, "Lumen Home")
sql/             # multi-tenant PostgreSQL schema, roles, seed data
tests/
customer_support_agent_guide.md   # full architecture guide
SPRINTS.md                        # sprint-by-sprint build plan
```

## Running it

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
```

Add a `.env` with your API keys:

```
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=...
```

Ingest the knowledge base (builds the local Chroma vector store):

```bash
uv run python src/ingest.py
```

Run the CLI:

```bash
uv run python src/agent.py
```

## Why this project

Built to learn agent architecture patterns beyond a single fixed prompt/pipeline: state graphs, tool-calling loops, multi-agent orchestration where specialists are independently customizable, grounding/hallucination mitigation via retrieval-distance confidence instead of self-reported LLM confidence, and the production concerns (multi-tenancy, RLS, human-in-the-loop approval for anything with real-world consequences like refunds) that separate a demo from something you'd trust with real customers.
