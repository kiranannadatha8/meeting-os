# Spec: MeetingOS — Multi-Agent Meeting Intelligence

> Status: Draft v1 · Owner: Kiran · Target: 4-week solo MVP, demo-ready

## Objective

Transform meeting transcripts into structured outputs (decisions, action items, summary) and dispatch follow-ups (tickets, emails) via a LangGraph-orchestrated agent graph that calls external tools through MCP. Replace the 20–40 minutes of manual post-meeting busywork with a single upload + review-and-approve flow that finishes in under a minute.

### Primary user

A knowledge worker (engineering manager, PM, founder) who runs 3–10 meetings per week and currently writes notes, extracts action items, and creates Linear tickets by hand afterward.

### User stories

1. **Upload** a transcript (`.txt`, `.vtt`) or audio (`.mp3`, `.wav`) → see decisions, action items, and a TL;DR within 60 seconds.
2. **Review** extracted action items in a table → edit owner/due date → one-click dispatch to Linear as tickets.
3. **Review** a draft follow-up email generated from the summary → approve/edit → send via Gmail.
4. **Search** across prior meetings semantically ("what did we decide about pricing last quarter?").

### Non-goals (MVP)

- Multi-tenant / teams / RBAC — single user, single workspace.
- Live meeting bots (Zoom / Google Meet join-and-record).
- Jira and Slack integrations — stretch only.
- Identity resolution for action-item owners — owner is a free-text string as said.
- Mobile app or native clients.
- Audit logs, billing, quota enforcement.

## Tech Stack

| Layer | Choice | Version | Notes |
|---|---|---|---|
| Web | Next.js | 14 (App Router) | TypeScript strict |
| Styling | Tailwind CSS | 3.x | No CSS modules |
| Auth | NextAuth.js | 4.x | Google OAuth only |
| Real-time | SSE via EventSource | — | No WebSockets for MVP |
| API | FastAPI | Python 3.11+ | Single service; no Node BFF; managed by uv |
| Queue | BullMQ + Redis | 7.x | Python worker consumes BullMQ queue |
| Transcription | OpenAI Whisper API | `whisper-1` | Audio-only ingestion path |
| Orchestration | LangGraph | latest | Parallel agent DAG |
| LLM | Anthropic Claude | `claude-sonnet-4-6` | All three agents, no routing |
| Tracing | LangSmith | — | Every agent run tagged with `meeting_id` |
| Tool dispatch | MCP | — | Linear + Gmail servers for MVP |
| DB | PostgreSQL + pgvector | 16 | Meetings, chunks, outputs, embeddings |
| Embeddings | OpenAI `text-embedding-3-small` | — | 1536-dim, cosine |
| Infra | Docker Compose (dev), GitHub Actions (CI) | — | Deploy to Railway **or** Fly.io (see Open Q5) |

## Commands

```bash
# Install
pnpm install
cd api && uv sync

# Dev — four terminals
docker compose up -d postgres redis                             # infra
pnpm dev:web                                                    # Next.js on :3000
cd api && uv run uvicorn app.main:app --reload --port 8000      # FastAPI
cd api && uv run python -m app.worker                           # agent worker

# Migrations
cd api && uv run alembic upgrade head
cd api && uv run alembic revision --autogenerate -m "<message>"

# Test
pnpm test:web
cd api && uv run pytest --cov=app --cov-report=term-missing

# Lint + typecheck
pnpm lint:web
cd api && uv run ruff check --fix && uv run mypy app

# Eval (5-meeting gold set → LangSmith)
cd api && uv run python -m app.eval.run

# Docker (full stack)
docker compose up --build

# E2E
pnpm --filter @meeting-os/web exec playwright test
```

## Project Structure

```
meeting-os/
├── web/                         # Next.js 14 app
│   ├── app/
│   │   ├── (auth)/              # NextAuth sign-in
│   │   ├── meetings/            # List + detail + results views
│   │   ├── search/              # Semantic search page
│   │   ├── settings/            # Integration API keys (Linear, Gmail)
│   │   └── api/                 # Route handlers — auth only; proxy rest to FastAPI
│   ├── components/              # React UI (StatusBadge, ActionItemTable, etc.)
│   ├── lib/                     # Client utils (fetch wrapper, useSSE, auth)
│   └── tests/                   # Vitest unit + Playwright e2e
├── api/                         # FastAPI service
│   ├── app/
│   │   ├── main.py              # FastAPI entry, router wiring
│   │   ├── worker.py            # BullMQ consumer loop
│   │   ├── routes/              # /meetings, /search, /integrations, /sse
│   │   ├── agents/              # decision.py, action_item.py, summary.py
│   │   ├── graph.py             # LangGraph DAG assembly
│   │   ├── mcp/                 # MCP client + linear.py, gmail.py wrappers
│   │   ├── ingestion/           # transcript parser, whisper adapter, chunker
│   │   ├── models/              # Pydantic (io) + SQLAlchemy (db) models
│   │   ├── db/                  # Alembic migrations, session
│   │   └── eval/                # Harness + gold dataset + scoring
│   └── tests/                   # pytest (unit + integration)
├── fixtures/                    # 5 demo transcripts + expected outputs (JSON)
├── docker-compose.yml
├── .github/workflows/           # lint.yml, test.yml, eval.yml
├── SPEC.md                      # This file — living document
└── README.md
```

## Code Style

### Python (FastAPI + agents)

Pydantic models for every structured LLM output. Dicts are never a contract.

```python
# api/app/agents/action_item.py
from datetime import date
from pydantic import BaseModel, Field

class ActionItem(BaseModel):
    title: str = Field(..., max_length=200)
    owner: str | None = Field(
        None,
        description="Name as said in transcript; not resolved to an identity.",
    )
    due_date: date | None = None
    source_quote: str = Field(..., description="Verbatim line from transcript.")

async def extract_action_items(transcript: str) -> list[ActionItem]:
    response = await claude.messages.create(
        model="claude-sonnet-4-6",
        response_model=list[ActionItem],
        messages=[{"role": "user", "content": _prompt(transcript)}],
    )
    return response
```

Rules:
- `ruff` + `mypy --strict` on `app/`
- `snake_case` files and functions, `PascalCase` classes
- No bare `except:` — catch specific exceptions and re-raise with context
- Prefer Pydantic models over `dict[str, Any]` at every boundary (route I/O, agent I/O, queue payload)
- Use `pathlib.Path`, never string paths
- `async def` for anything that hits the network or DB

### TypeScript (Next.js)

```tsx
// web/components/MeetingStatus.tsx
type MeetingStatus = 'queued' | 'processing' | 'complete' | 'failed';

type Props = {
  meetingId: string;
  initialStatus: MeetingStatus;
};

export function MeetingStatus({ meetingId, initialStatus }: Props) {
  const status = useMeetingStatusSSE(meetingId, initialStatus);
  return <StatusBadge value={status} />;
}
```

Rules:
- `strict: true` in `tsconfig.json`; no `any`, no `@ts-ignore`
- Function components only
- Server Components by default; `'use client'` only for SSE, forms, and local state
- Tailwind utility classes only — no CSS modules for MVP
- `PascalCase` for components, `camelCase` for hooks/utils, `kebab-case` for file names of non-component modules

### Universal

- Files under 400 lines; split aggressively
- Immutable data — return new objects, never mutate
- Every exported function has an explicit signature
- Comments only for non-obvious WHY; code explains WHAT

## Testing Strategy

**Coverage target:** 80% lines on `api/app/`, 70% on `web/`.

### Pyramid

| Level | Framework | Location | Covers |
|---|---|---|---|
| Unit | pytest, Vitest | `*/tests/unit/` | Pure functions: parsers, chunkers, prompt builders, formatters |
| Integration | pytest + testcontainers | `api/tests/integration/` | Routes against real Postgres + Redis, LangGraph with mocked LLM |
| Agent eval | Custom harness | `api/app/eval/` | 5-meeting gold set; fuzzy-match extracted items vs expected |
| E2E | Playwright | `web/tests/e2e/` | Upload → process → results → one approve-and-dispatch flow |

### Rules

- LLM calls are **mocked** in unit and integration tests with recorded fixtures — only `eval/` hits Claude.
- Eval runs on every PR that touches `agents/`, `graph.py`, or prompt files; nightly on main.
- External integrations (Linear, Gmail) are quarantined and skipped unless integration credentials are present in the test env.

### Gates

- Merge blocked if line coverage drops more than 2 percentage points vs main.
- Merge blocked if eval score drops more than 5 percentage points vs main.

## Boundaries

### Always do

- Write a failing test before adding a new route, agent, or MCP tool.
- Run `ruff`, `mypy`, and `pnpm lint` locally before committing.
- Use Pydantic models for every LLM structured output; no free-form JSON parsing.
- Require a user approval click in the UI before any MCP tool dispatches to an external system.
- Log the LangSmith run ID on every agent invocation and include it in the API response.
- Use parameterized SQL via SQLAlchemy — never string-concatenate into queries.
- Update SPEC.md in the same PR that changes architecture or scope.

### Ask first

- Adding a new runtime (reviving the Node BFF, introducing a Rust/Go service).
- Changing the agent DAG shape (serializing currently-parallel nodes, adding a fourth agent).
- Swapping the model (e.g. Sonnet → Opus, or Claude → OpenAI).
- Adding an MCP integration beyond Linear + Gmail.
- Any schema migration (new table, altered column, index change).
- Adding a paid dependency or new external API beyond Claude, OpenAI Whisper, Linear, Gmail.

### Never do

- Commit API keys, OAuth client secrets, or `.env` files — `.env.local` is gitignored.
- Dispatch to an external system (Linear, Gmail) without an explicit user approval click.
- Store raw audio beyond transcription — delete the blob once Whisper returns text.
- Auto-retry an LLM call more than 3× without circuit-breaking — cost exposure is real.
- Use `--no-verify` on git commits, or `--force` on shared branches.
- Claim an eval improvement in a PR without committing the new score.

## Architecture decisions (load-bearing)

1. **Agents run truly parallel on the raw transcript.** Decision, action-item, and summary agents each read the full transcript independently. A post-merge step enriches the summary with references to extracted decision/action IDs. Chosen for simpler graph + faster wall-clock time; tradeoff is the summary agent can't cite the others' outputs directly (accepted for MVP).
2. **No Node.js BFF.** Next.js route handlers cover auth and webhooks; all business logic lives in FastAPI. Re-add a Node layer only if the Zoom/Meet bot lands (deferred past MVP).
3. **Owner is free-text, not an identity.** The LLM extracts "Kiran" as the owner string; there is no user-matching table. Identity resolution is a post-MVP feature.
4. **Single model (Claude Sonnet 4.6) everywhere.** No cost-based routing. Cost of three Sonnet calls per 30-min transcript is acceptable at demo scale.
5. **Audio path is first-class, bot path is cut.** `.mp3/.wav` upload → Whisper → same pipeline as text. Zoom/Meet live bots are README roadmap only.

## Success criteria

Demo-ready means all six are true:

1. **Latency** — 30-minute transcript → decisions + actions + summary in ≤60s p50, ≤90s p95 on the eval set.
2. **Quality** — ≥90% recall on human-labeled action items; ≥80% on decisions (measured by eval harness).
3. **Human-in-the-loop** — Every external dispatch (Linear ticket, Gmail draft) shows an approve / edit / skip step in the UI.
4. **Search** — Semantic query over ≥5 ingested meetings returns the correct meeting in top-3 results for 5/5 canned test queries.
5. **Polish** — Public GitHub README with architecture diagram, a 2–3 minute Loom demo, and a live deployed URL.
6. **Reliability** — CI green on `main`; `docker compose up` boots the full stack in under 60s on a fresh clone.

## Open questions

1. **Eval gold set authoring** — do we have 5 real (redacted) transcripts, or should we synthesise them with GPT? Affects Week 1 scheduling.
2. **Semantic search UI** — standalone `/search` page, or inline filter on the meeting list? Defaulting to standalone.
3. **Action-item editing** — inline edit before approving dispatch, or approve-as-is? Defaulting to inline edit.
4. **LangSmith projects** — `meeting-os-dev` and `meeting-os-prod`, OK?
5. **Deploy target** — Railway or Fly.io? Railway is faster to set up; Fly has better regional control. Defaulting to Railway for speed.

---

*Last updated: 2026-04-14 · Edit this file in the same PR that changes scope or architecture.*
