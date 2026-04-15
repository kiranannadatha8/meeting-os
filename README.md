# MeetingOS

Multi-agent meeting intelligence. Upload a transcript, get decisions, action items, a summary, and dispatch follow-ups via MCP tools — all in under 60 seconds.

See **[SPEC.md](SPEC.md)** for the full specification and **[PLAN.md](PLAN.md)** for the 25-task implementation plan.

## Status

🚧 **Active development** — current phase: **W1 Foundation**. See [PLAN.md](PLAN.md) for what's shipping this week.

## Prerequisites

- Node.js 20+ — `nvm use` picks up [.nvmrc](.nvmrc)
- Python 3.11+ — managed automatically by uv
- Docker Desktop
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [pnpm](https://pnpm.io/installation) — `brew install pnpm`

## Install

```bash
pnpm install
cd api && uv sync
```

## Run (four terminals)

1. **Infra** — `docker compose up -d postgres redis`
2. **API** — `cd api && uv run uvicorn app.main:app --reload --port 8000`
3. **Worker** — `cd api && uv run python -m app.worker`
4. **Web** — `pnpm dev:web`

Then open http://localhost:3000.

## Environment

Copy [.env.example](.env.example) to `.env.local` and fill in the values you need. W1 Foundation runs without any external API keys — they're only required as later phases light up (see inline comments in `.env.example`).

## Project structure

```
web/                  Next.js 14 (App Router) frontend
api/                  FastAPI agent orchestration + ingestion
fixtures/             Demo transcripts + eval gold set
docker-compose.yml    postgres+pgvector + redis
```

## Testing

```bash
# Python
cd api && uv run pytest

# Web (from root)
pnpm test:web
```

## Documentation

- [SPEC.md](SPEC.md) — objective, tech stack, commands, code style, testing strategy, boundaries
- [PLAN.md](PLAN.md) — 4-week roadmap, 25 tasks, dependency graph, risks

## License

TBD.
