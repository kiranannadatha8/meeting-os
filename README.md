# MeetingOS

Multi-agent meeting intelligence. Upload a transcript (or audio), get decisions, action items, and a summary in under 60 seconds — then dispatch follow-ups to Linear or Gmail through a human approval step.

See **[SPEC.md](SPEC.md)** for the full specification and **[PLAN.md](PLAN.md)** for the 25-task implementation roadmap.

## Quick start (Docker)

```bash
git clone <repo-url>
cd meeting-os
cp .env.example .env
# Generate a 32-byte Fernet key for MEETING_OS_ENCRYPTION_KEY:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build
```

The full stack — Postgres+pgvector, Redis, FastAPI, the BullMQ worker, and Next.js — boots in **~15 seconds** on a warm cache. Open http://localhost:3000.

External API keys (Anthropic, OpenAI, Google OAuth, Linear, Gmail) are optional for boot but required as features light up. Every variable is documented inline in [`.env.example`](.env.example).

## Architecture

```
┌──────────────┐      upload       ┌──────────────┐    enqueue    ┌──────────────┐
│              │ ────────────────► │              │ ────────────► │              │
│   Next.js    │                   │   FastAPI    │               │   BullMQ     │
│  (App Router)│ ◄──────────────── │   (routes)   │               │   + Redis    │
│              │   SSE status      │              │               │              │
└──────┬───────┘                   └──────┬───────┘               └──────┬───────┘
       │                                  │                              │
       │                                  │ read/write                   │ consume
       │                                  ▼                              ▼
       │                           ┌──────────────┐               ┌──────────────┐
       │                           │ Postgres +   │               │ Python       │
       │                           │ pgvector     │ ◄──────────── │ worker       │
       │                           │ (meetings,   │    persist    │              │
       │                           │  chunks,     │               │ ┌──────────┐ │
       │                           │  decisions,  │               │ │LangGraph │ │
       │                           │  actions,    │               │ │  DAG     │ │
       │                           │  summaries,  │               │ └────┬─────┘ │
       │                           │  integrations│               │      │       │
       │                           │  vectors)    │               │ ┌────▼─────┐ │
       │                           └──────────────┘               │ │parallel  │ │
       │ dispatch approved                                        │ │agents    │ │
       │  (Linear / Gmail)                                        │ │(decision,│ │
       └──────────────────────────────────────────────────────────┤ │action,   │ │
                                                                  │ │summary)  │ │
                                                                  │ └──────────┘ │
                                                                  └──────┬───────┘
                                                                         │
                                                                         ▼
                                                                  ┌──────────────┐
                                                                  │ Claude +     │
                                                                  │ OpenAI +     │
                                                                  │ MCP tools    │
                                                                  └──────────────┘
```

- **Next.js 14** — App Router. Route handlers cover auth (NextAuth + Google OAuth) and proxy the rest to FastAPI. `useSSE` reads real-time status from the API.
- **FastAPI** — Single Python service; owns ingestion, agent orchestration, MCP tool dispatch, and semantic search over pgvector.
- **BullMQ + Python worker** — Long-running pipeline (chunk → embed → run LangGraph DAG) pulled off the request path.
- **LangGraph DAG** — Decision, action-item, and summary agents run on Claude Sonnet 4.6 in parallel against the raw transcript; post-merge step enriches the summary with extracted IDs.
- **MCP integrations** — Encrypted per-user credentials for Linear and Gmail, dispatched behind a human approve/edit/skip step in the UI.

See SPEC.md §"Tech Stack" for the full stack, and §"Architecture decisions" for the load-bearing choices.

## Demo walkthrough

1. Sign in with Google at http://localhost:3000 (requires `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).
2. Upload a `.txt`, `.vtt`, `.mp3`, or `.wav` — for a quick demo, try [`fixtures/gold/*.txt`](fixtures/gold/).
3. Watch the meeting card flip from `queued` → `processing` → `complete` (SSE-driven, no polling).
4. Open the meeting to see the generated summary, decisions, and action items with quotes linked back to the transcript.
5. In **Settings**, paste a Linear API key or Gmail refresh token to light up tool dispatch — every external call shows an approve/edit/skip step.
6. Use **Search** to run a semantic query across ingested meetings.

## Local development (no Docker)

If you'd rather run the services directly:

```bash
# Prerequisites — Node 20+ (nvm use), Python 3.11+, Docker Desktop,
#   uv (curl -LsSf https://astral.sh/uv/install.sh | sh), pnpm (brew install pnpm)

# Install
pnpm install
cd api && uv sync

# Four terminals
docker compose up -d postgres redis                             # infra only
cd api && uv run alembic upgrade head                           # migrations
cd api && uv run uvicorn app.main:app --reload --port 8000      # API
cd api && uv run python -m app.worker                           # worker
pnpm dev:web                                                    # web on :3000
```

## Environment

Copy [.env.example](.env.example) to `.env` and fill in the values you need. The file lists every supported variable, grouped by the feature that unlocks it.

## Testing

```bash
# Python — unit + integration (starts a real Postgres via docker compose)
cd api && uv run pytest

# Web — Vitest
pnpm test:web

# Eval harness — 5-meeting gold set against the current agent wiring
cd api && uv run python -m app.eval.run
```

CI runs `lint`, `test`, and (on agent-touching PRs) `eval` on every push to `main` and every PR — see [`.github/workflows/`](.github/workflows/).

## Project structure

```
web/                     Next.js 14 (App Router) frontend
api/                     FastAPI — routes, agents, ingestion, MCP, eval
fixtures/                Demo transcripts + gold-set expected outputs
docker-compose.yml       postgres + redis + api + worker + web
.github/workflows/       CI (lint, test, eval)
SPEC.md                  Living spec
PLAN.md                  25-task roadmap
```

## Documentation

- [SPEC.md](SPEC.md) — objective, tech stack, code style, testing strategy, boundaries
- [PLAN.md](PLAN.md) — 4-week roadmap, dependency graph, risks

## License

TBD.
