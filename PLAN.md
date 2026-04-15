# Implementation Plan: MeetingOS

> Companion to [SPEC.md](./SPEC.md). 25 tasks across 4 phases (~1 week each). Update this file in the same PR that changes scope.

## Overview

Build MeetingOS MVP in 25 vertical-sliced tasks over 4 weeks. Week 1 gets a stubbed end-to-end path (upload → queue → placeholder agents → UI) so every integration seam is exercised early. Week 2 replaces the placeholders with real Claude-powered agents and ships the eval harness alongside. Week 3 adds MCP tool dispatch with human-in-the-loop approval. Week 4 is polish, search, and ship.

## Architecture decisions (from SPEC.md, restated for context)

- Parallel agent DAG on raw transcript; summary enriched with refs in a post-merge pass
- No Node BFF — Next.js route handlers + FastAPI only
- Single model (Claude Sonnet 4.6) across all agents
- MCP integrations: Linear + Gmail for MVP (Jira + Slack deferred)
- Audio path via Whisper is first-class; meeting-bot path is deferred

## Parallelization opportunities

- **T03 (FastAPI skeleton) ‖ T04 (Next.js + NextAuth)** — no shared code until T05
- **T11 ‖ T12 ‖ T13** — three agents are independent; same interface, different prompts
- **T18 ‖ T19** — Linear and Gmail MCP tools share the client but nothing else
- **T21 ‖ T22** — semantic search and SSE are independent surfaces

---

## Phase 1: Foundation (Week 1) — ingest to DB

Goal: a user can upload a transcript, see it appear in a list, and watch its status flip from `queued` → `processing` → `complete`. Agents are stubbed (return empty arrays).

### Task 01: Monorepo scaffold
**Description:** Initialize the `web/` and `api/` workspaces, root `docker-compose.yml` with Postgres+pgvector and Redis, `fixtures/` directory, `.env.example`, `.gitignore`, and empty CI workflow stubs.
**Acceptance:**
- [ ] `pnpm install` and `cd api && poetry install` both succeed on a fresh clone
- [ ] `docker compose up -d postgres redis` brings up healthy containers
- [ ] Root `README.md` explains the four dev terminals
**Verification:** `docker compose ps` shows `healthy` for both services.
**Dependencies:** None
**Files:** `web/package.json`, `api/pyproject.toml`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`
**Scope:** S

### Task 02: Database schema + Alembic baseline
**Description:** Create initial schema with tables for `meetings`, `chunks` (with `pgvector` embedding column), `decisions`, `action_items`, `summaries`, `integrations` (encrypted API keys). Wire Alembic.
**Acceptance:**
- [ ] `alembic upgrade head` creates all tables cleanly
- [ ] `pgvector` extension is enabled via migration
- [ ] Foreign keys and indexes defined (meeting_id FKs, vector index on chunks.embedding)
**Verification:** `poetry run alembic upgrade head && poetry run alembic downgrade base` is clean both directions.
**Dependencies:** T01
**Files:** `api/app/db/models.py`, `api/alembic/versions/0001_init.py`, `api/alembic.ini`
**Scope:** M

### Task 03: FastAPI skeleton + Pydantic models ‖ parallelizable with T04
**Description:** FastAPI app with `/health`, CORS, structured logging, Pydantic base models for all I/O contracts (MeetingCreate, MeetingOut, ActionItem, Decision, Summary).
**Acceptance:**
- [ ] `GET /health` returns `{"status":"ok"}`
- [ ] OpenAPI docs render at `/docs`
- [ ] All I/O Pydantic models defined (even if unused yet)
**Verification:** `pytest api/tests/unit/test_health.py` passes; `curl localhost:8000/health` returns 200.
**Dependencies:** T01
**Files:** `api/app/main.py`, `api/app/models/io.py`, `api/app/routes/health.py`, `api/tests/unit/test_health.py`
**Scope:** S

### Task 04: Next.js skeleton + NextAuth Google OAuth ‖ parallelizable with T03
**Description:** Next.js 14 App Router scaffold, Tailwind configured, NextAuth with Google provider, protected route pattern, sign-in page.
**Acceptance:**
- [ ] Unauthenticated users hitting `/meetings` redirect to `/signin`
- [ ] Google OAuth flow completes and creates a session cookie
- [ ] Tailwind utility classes render correctly
**Verification:** Manual: sign in with Google; confirm session in browser devtools.
**Dependencies:** T01
**Files:** `web/app/layout.tsx`, `web/app/(auth)/signin/page.tsx`, `web/app/api/auth/[...nextauth]/route.ts`, `web/lib/auth.ts`
**Scope:** M

### Task 05: Transcript upload route + job enqueue
**Description:** `POST /meetings` accepts `multipart/form-data` with `.txt` or `.vtt`, persists a Meeting row with `status='queued'`, pushes a job onto the BullMQ queue (via redis-py), returns 201 with meeting ID.
**Acceptance:**
- [ ] Valid upload returns 201 with `{"id": "...", "status": "queued"}`
- [ ] Invalid file extension returns 422
- [ ] Redis queue shows the job payload
**Verification:** `pytest api/tests/integration/test_upload.py` with testcontainers Postgres+Redis.
**Dependencies:** T02, T03
**Files:** `api/app/routes/meetings.py`, `api/app/ingestion/parser.py`, `api/app/queue.py`, `api/tests/integration/test_upload.py`
**Scope:** M

### Task 06: BullMQ worker + status transitions
**Description:** Python worker process consumes from BullMQ queue, marks meeting `processing`, runs a stub pipeline (no-op), marks `complete`. Handles crashes by marking `failed`.
**Acceptance:**
- [ ] Worker picks jobs from queue and processes them
- [ ] Meeting status transitions queued → processing → complete
- [ ] Intentional exception results in `failed` status + error logged
**Verification:** `pytest api/tests/integration/test_worker.py` simulates a successful + failing job.
**Dependencies:** T05
**Files:** `api/app/worker.py`, `api/app/pipeline.py` (stub), `api/tests/integration/test_worker.py`
**Scope:** M

### Task 07: Chunking + embedding pipeline
**Description:** Replace the T06 stub with real chunking (500-token windows, 50-token overlap) and embedding via OpenAI `text-embedding-3-small`. Writes rows to `chunks` table.
**Acceptance:**
- [ ] A 30-min transcript produces ~60-120 chunks with embeddings
- [ ] Embedding call failures trigger retry (max 3) then `failed` status
- [ ] Embeddings are persisted and queryable via `SELECT embedding <=> '...' FROM chunks`
**Verification:** `pytest api/tests/integration/test_pipeline.py` — mock OpenAI, assert chunk count + row writes.
**Dependencies:** T06
**Files:** `api/app/ingestion/chunker.py`, `api/app/ingestion/embedder.py`, `api/app/pipeline.py`, `api/tests/integration/test_pipeline.py`
**Scope:** M

### Task 08: Meeting list UI
**Description:** `/meetings` page renders a table of uploaded meetings with name, created-at, status badge. Upload button triggers file picker → POSTs to FastAPI via Next.js proxy.
**Acceptance:**
- [ ] Logged-in user sees their own meetings
- [ ] Uploading a file adds a row with `queued` status
- [ ] Status auto-refreshes every 3s (polling for now — replaced by SSE in T22)
**Verification:** Vitest unit tests for `MeetingTable` (status badges + polling) and the `/api/meetings` route handler (POST proxy). Playwright e2e for the upload flow is deferred to T15, when the Playwright harness is introduced for the results page (one setup amortised across both tests).
**Dependencies:** T04, T05
**Files:** `web/app/meetings/page.tsx`, `web/components/MeetingTable.tsx`, `web/components/UploadButton.tsx`, `web/app/api/meetings/route.ts`, `web/tests/unit/MeetingTable.test.tsx`, `web/tests/unit/api-meetings-route.test.ts`, plus `api/app/routes/meetings.py` (extend with `GET /meetings`)
**Scope:** M

### Task 09: Whisper audio ingestion path
**Description:** Extend upload route to accept `.mp3` and `.wav`. Worker detects audio content type and runs Whisper transcription before chunking. Deletes the audio blob after transcription.
**Acceptance:**
- [ ] `.mp3` upload produces a transcribed text that feeds the rest of the pipeline
- [ ] Audio file is deleted from disk/storage after transcription succeeds
- [ ] File size limit of 25MB enforced
**Verification:** `pytest` with a short (~10s) fixture audio file, Whisper mocked.
**Dependencies:** T07
**Files:** `api/app/ingestion/whisper_adapter.py`, `api/app/ingestion/parser.py` (extend), `api/tests/integration/test_audio.py`
**Scope:** S

### Checkpoint: End of Week 1
- [ ] `docker compose up` boots full stack in <60s
- [ ] User can sign in, upload `.txt`/`.vtt`/`.mp3`, see it land in the list, watch status transition
- [ ] All chunks + embeddings persisted to pgvector
- [ ] Coverage ≥70% on `api/app/ingestion/` and `api/app/routes/`
- [ ] **Review with human before proceeding to Phase 2**

---

## Phase 2: Agents (Week 2) — LangGraph pipeline

Goal: replace the no-op stub with a real three-agent parallel graph. Eval harness ships in the same week so every prompt tweak has a score.

### Task 10: LangGraph graph skeleton with parallel no-op nodes
**Description:** Define the DAG: `load_transcript` → (parallel: `decision_node`, `action_node`, `summary_node`) → `merge` → `persist`. Nodes return empty structured output. Wire into `pipeline.py`.
**Acceptance:**
- [ ] `graph.py` defines the DAG with typed state
- [ ] All three nodes execute (even returning empty data)
- [ ] Merge step writes placeholder rows to `decisions`, `action_items`, `summaries`
**Verification:** Unit test asserts graph runs end-to-end with test transcript.
**Dependencies:** T07
**Files:** `api/app/graph.py`, `api/app/agents/__init__.py`, `api/app/agents/_base.py`, `api/tests/unit/test_graph.py`
**Scope:** S

### Task 11: Decision extraction agent ‖ parallelizable with T12, T13
**Description:** Implement `decision_node` — prompt Claude Sonnet 4.6 with transcript, receive structured `list[Decision]` via Pydantic. Include retry + fallback to empty list on parse failure.
**Acceptance:**
- [ ] Given a transcript with ≥3 clear decisions, returns ≥3 `Decision` rows
- [ ] Pydantic validation enforces schema (title, rationale, source_quote)
- [ ] 3-retry limit; structured errors logged
**Verification:** Unit test with recorded fixture; `eval/` target for decision recall.
**Dependencies:** T10
**Files:** `api/app/agents/decision.py`, `api/app/agents/prompts/decision.md`, `api/tests/unit/test_decision_agent.py`
**Scope:** M

### Task 12: Action item agent ‖ parallelizable with T11, T13
**Description:** Implement `action_node` — extract `list[ActionItem]` with title, owner (free-text), due_date (parsed to `date | None`), source_quote.
**Acceptance:**
- [ ] Due-date heuristics parse "by Friday", "next Tuesday", "2026-05-01" into `date` objects
- [ ] Owner extracted as free-text name ("Kiran", "the infra team")
- [ ] Items without explicit owner return `owner=None` rather than hallucinating
**Verification:** Unit test with fixture transcript of 5 action items.
**Dependencies:** T10
**Files:** `api/app/agents/action_item.py`, `api/app/agents/prompts/action_item.md`, `api/tests/unit/test_action_agent.py`
**Scope:** M

### Task 13: Summary agent + post-merge reference enrichment ‖ parallelizable with T11, T12
**Description:** Implement `summary_node` producing TL;DR + bullet highlights. Merge step enriches summary text with `[[decision:N]]` / `[[action:N]]` markers referring to other agents' IDs when quotes overlap.
**Acceptance:**
- [ ] Summary contains TL;DR (≤100 words) + 3-7 highlight bullets
- [ ] Merge step inserts reference markers where quote overlap >80%
- [ ] Summary renders without broken refs if overlap logic skips a link
**Verification:** Unit test for summary agent + integration test for merge enrichment.
**Dependencies:** T10, T11, T12
**Files:** `api/app/agents/summary.py`, `api/app/agents/prompts/summary.md`, `api/app/agents/merge.py`, `api/tests/unit/test_summary_agent.py`
**Scope:** M

### Task 14: LangSmith tracing
**Description:** Wire LangSmith env vars (`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT=meeting-os-dev`). Every agent run is tagged with `meeting_id` metadata. Run ID surfaces in API response.
**Acceptance:**
- [ ] LangSmith dashboard shows runs grouped by `meeting_id`
- [ ] API response `GET /meetings/{id}` includes `langsmith_run_ids` field
**Verification:** Manual: trigger pipeline, open LangSmith, confirm trace visible.
**Dependencies:** T11, T12, T13
**Files:** `api/app/graph.py` (extend), `api/app/models/io.py` (extend)
**Scope:** XS

### Task 15: Results UI — decisions + action items + summary
**Description:** `/meetings/[id]` page renders decision cards, action-item table, summary panel. Handles in-progress and failed states.
**Acceptance:**
- [ ] Complete meeting shows all three sections populated
- [ ] Processing meeting shows per-agent skeleton loaders
- [ ] Failed meeting shows error with retry button
**Verification:** Playwright e2e asserts all three sections render from a fixture meeting.
**Dependencies:** T13
**Files:** `web/app/meetings/[id]/page.tsx`, `web/components/DecisionCard.tsx`, `web/components/ActionItemTable.tsx`, `web/components/SummaryPanel.tsx`, `web/tests/e2e/results.spec.ts`
**Scope:** M

### Task 16: Eval harness + 5 gold fixtures
**Description:** Build `api/app/eval/` with runner, scorer, and 5 transcript fixtures with human-labeled expected output. Scorer computes recall/precision with fuzzy-string matching (rapidfuzz ratio > 80). Outputs JSON report + LangSmith annotations.
**Acceptance:**
- [ ] `poetry run python -m app.eval.run` produces a JSON scorecard
- [ ] Baseline scores committed to `fixtures/eval_baseline.json`
- [ ] CI job runs eval and fails if score drops >5pp vs baseline
**Verification:** Eval runs locally; CI job runs in a dedicated workflow.
**Dependencies:** T11, T12, T13
**Files:** `api/app/eval/run.py`, `api/app/eval/scorer.py`, `fixtures/eval/transcript_*.txt`, `fixtures/eval/expected_*.json`, `.github/workflows/eval.yml`
**Scope:** M

### Checkpoint: End of Week 2
- [ ] All three agents produce real structured output on fixture transcripts
- [ ] Eval harness runs green; baseline committed
- [ ] LangSmith traces visible for every run
- [ ] Results UI renders decisions, action items, summary cleanly
- [ ] **Review with human before proceeding to Phase 3**

---

## Phase 3: MCP tool dispatch (Week 3) — Linear + Gmail with approval

Goal: users can one-click dispatch action items to Linear as tickets and approve/edit a Gmail draft — always behind an explicit approval step.

### Task 17: MCP client wiring + integration settings UI
**Description:** MCP client singleton in FastAPI, integration-settings page in Next.js for Linear API key + Gmail OAuth. Keys encrypted at rest (AES-GCM via env-provided key).
**Acceptance:**
- [ ] `/settings` page has fields for Linear API key + "Connect Gmail" button
- [ ] Keys persisted encrypted in `integrations` table
- [ ] FastAPI `/integrations/status` returns which tools are configured
**Verification:** Playwright asserts settings flow round-trips keys.
**Dependencies:** T04
**Files:** `api/app/mcp/client.py`, `api/app/routes/integrations.py`, `web/app/settings/page.tsx`, `web/tests/e2e/settings.spec.ts`
**Scope:** M

### Task 18: Linear MCP tool — ticket creation ‖ parallelizable with T19
**Description:** MCP tool wrapper for Linear `create_issue`. Accepts `list[ActionItem]` + target team, returns created issue URLs.
**Acceptance:**
- [ ] Calling tool with N action items creates N Linear issues in a test workspace
- [ ] Errors (bad API key, missing team) surface as structured errors to UI
- [ ] Integration test skipped if `LINEAR_TEST_API_KEY` not set
**Verification:** Integration test with `LINEAR_TEST_API_KEY` hitting a throwaway Linear workspace.
**Dependencies:** T17
**Files:** `api/app/mcp/linear.py`, `api/app/routes/dispatch.py`, `api/tests/integration/test_linear.py`
**Scope:** M

### Task 19: Gmail MCP tool — draft follow-up email ‖ parallelizable with T18
**Description:** MCP tool wrapper for Gmail `create_draft`. Accepts summary + recipient list, produces a draft in the user's Gmail drafts folder (does NOT send).
**Acceptance:**
- [ ] Draft appears in Gmail drafts folder of test account
- [ ] Draft contains TL;DR + bullet highlights + action item list
- [ ] Integration test skipped without `GMAIL_TEST_REFRESH_TOKEN`
**Verification:** Integration test against a throwaway Gmail account.
**Dependencies:** T17
**Files:** `api/app/mcp/gmail.py`, `api/tests/integration/test_gmail.py`
**Scope:** M

### Task 20: Approval UI for dispatch
**Description:** Buttons on the results page — "Create Linear tickets", "Draft Gmail follow-up". Each opens a modal showing exactly what will be sent with per-item checkboxes. Action only fires on explicit confirmation.
**Acceptance:**
- [ ] Modal shows exact payload (title, body, recipient) before send
- [ ] User can deselect individual items before confirming
- [ ] Successful dispatch shows resulting URLs inline
- [ ] No external call fires without click confirmation
**Verification:** Playwright e2e tests the dispatch flow with MCP tools mocked.
**Dependencies:** T15, T18, T19
**Files:** `web/components/DispatchModal.tsx`, `web/app/meetings/[id]/page.tsx` (extend), `web/tests/e2e/dispatch.spec.ts`
**Scope:** M

### Checkpoint: End of Week 3
- [ ] Linear tickets land in a throwaway workspace from one click
- [ ] Gmail drafts appear in a throwaway account from one click
- [ ] No dispatch fires without explicit user confirmation
- [ ] Integration tests green with real credentials (optional in CI)
- [ ] **Review with human before proceeding to Phase 4**

---

## Phase 4: Polish + ship (Week 4)

Goal: real-time status, semantic search, CI green, deployed URL, Loom demo.

### Task 21: Semantic search route + UI ‖ parallelizable with T22
**Description:** `GET /search?q=...` embeds query, returns top-5 chunks by cosine distance + meeting metadata. `/search` page renders results with highlighted snippet.
**Acceptance:**
- [ ] Query "pricing" returns meetings that discussed pricing in top 3
- [ ] Snippet shows the matching chunk with the query terms highlighted
- [ ] Empty result state rendered gracefully
**Verification:** 5 canned queries run against the 5 demo meetings — each returns the expected meeting in top-3.
**Dependencies:** T07
**Files:** `api/app/routes/search.py`, `web/app/search/page.tsx`, `api/tests/integration/test_search.py`
**Scope:** M

### Task 22: SSE real-time status ‖ parallelizable with T21
**Description:** Replace 3s polling with `GET /meetings/{id}/events` SSE stream emitting status transitions + per-agent progress. Client uses `EventSource`.
**Acceptance:**
- [ ] Meeting detail page updates instantly when worker advances status
- [ ] Reconnect on transient disconnect
- [ ] No polling left in the client
**Verification:** Manual: upload a transcript, watch status update without refresh.
**Dependencies:** T08, T15
**Files:** `api/app/routes/sse.py`, `web/lib/useSSE.ts`, `web/app/meetings/[id]/page.tsx` (extend)
**Scope:** S

### Task 23: CI pipeline — lint, test, eval
**Description:** GitHub Actions workflows for (a) lint + typecheck, (b) unit + integration tests with service containers, (c) eval on every PR to `agents/` or prompts.
**Acceptance:**
- [ ] `lint.yml` fails on ruff/mypy/eslint/tsc errors
- [ ] `test.yml` runs pytest + vitest with Postgres + Redis service containers
- [ ] `eval.yml` runs eval harness on PRs touching prompts/agents
- [ ] All workflows green on `main`
**Verification:** Open a PR that intentionally breaks lint → CI fails. Revert → CI green.
**Dependencies:** T16
**Files:** `.github/workflows/lint.yml`, `.github/workflows/test.yml`, `.github/workflows/eval.yml`
**Scope:** S

### Task 24: Docker Compose full-stack + public README
**Description:** Single `docker compose up` boots postgres+pgvector, redis, api, worker, web. README has architecture diagram, quick-start, demo fixtures instructions.
**Acceptance:**
- [ ] Fresh clone → `docker compose up` → app usable at localhost:3000 in <60s
- [ ] README has architecture diagram (from the SPEC), commands, demo walkthrough
- [ ] `.env.example` documents every required env var
**Verification:** Fresh clone on a clean machine boots full stack.
**Dependencies:** T22
**Files:** `docker-compose.yml` (extend), `api/Dockerfile`, `web/Dockerfile`, `README.md`
**Scope:** S

### Task 25: Deploy to Railway + 5 demo meetings + Loom
**Description:** Provision Railway project with Postgres+pgvector + Redis addons. Deploy web + api + worker services. Seed 5 demo meetings. Record 2-3 minute Loom walkthrough.
**Acceptance:**
- [ ] Public URL reachable and sign-in works
- [ ] 5 pre-processed demo meetings visible on a shared demo account
- [ ] Loom link in README; README has "Try it" section with demo-account creds (read-only)
**Verification:** Share Loom + URL with a friend; they can sign in and explore without help.
**Dependencies:** T23, T24
**Files:** `railway.toml`, `README.md` (extend), Loom URL
**Scope:** S

### Checkpoint: Done
- [ ] All success criteria from SPEC.md met
- [ ] CI green on `main`
- [ ] Eval score ≥ SPEC targets (90% action-item recall, 80% decision recall)
- [ ] Public URL + Loom + README live
- [ ] **Ship it**

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| MCP client library API churn during build | High | Wrap MCP in a thin adapter (`api/app/mcp/client.py`); swap internals without touching agents |
| LangGraph parallel-node quirks (blocking, shared state races) | Med | Build T10 skeleton first with no-op nodes to validate parallelism before adding Claude calls |
| Anthropic rate limits during eval runs | Med | Cache eval responses in fixtures; only rerun on prompt/model changes; nightly full-eval job |
| NextAuth session ↔ FastAPI auth mismatch | Med | Pass session through Next.js route handlers as proxy; FastAPI trusts shared JWT signing key |
| Whisper cost/latency on long audio | Low | 25MB limit enforced in T09; chunk audio if >25MB is ever needed (post-MVP) |
| pgvector index performance | Low | HNSW index on `chunks.embedding`; not a concern at 5-meeting scale |
| Gmail OAuth approval friction during demo | Med | Use a throwaway Gmail account with the token pre-baked into demo env |
| Railway cold starts on free tier | Low | Accept 2-3s cold start for demo; upgrade tier only if it bites during Loom |

## Open questions (deferred from SPEC)

1. Gold-set transcripts — real redacted, or GPT-synthesised? Answer unblocks T16.
2. Semantic search UI — standalone `/search` or inline filter? Plan assumes standalone (T21).
3. Action-item editing pre-dispatch — inline edit or approve-as-is? Plan assumes inline edit (T20).

## How to consume this plan

- Work **top-to-bottom within a phase**; skip only when a parallelization marker (‖) says so.
- Every task completion should be a PR that references the task number in the title (`T07: chunking + embedding pipeline`).
- Update this file in the same PR when scope shifts — do not let the plan drift from the code.
- At each checkpoint, run the checklist and pause for human review before advancing.

---

*Last updated: 2026-04-14 · Living document — keep it in sync with reality.*
