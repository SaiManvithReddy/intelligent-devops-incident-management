# Intelligent DevOps Incident Management System

An AI-powered incident management pipeline that ingests server logs and system
telemetry, classifies every event by severity using LangChain + OpenAI, persists
structured incident records to PostgreSQL, exposes a FastAPI REST API for on-call
tooling, and displays a real-time React dashboard with severity breakdown charts
and MTTR metrics.

**No OpenAI API key required** — the system automatically falls back to a
`MockClassifier` that produces realistic-looking classifications without any paid
API access or network connectivity. The entire stack can run end-to-end purely with
Docker Compose.

---

## Architecture

```
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  Log Producers (simulated)                                               │
  │  ┌─────────────────┐    ┌────────────────────────────────────────────┐  │
  │  │  Sample .log     │    │  Redis-backed message queue                │  │
  │  │  files under     │    │  (LPUSH / BRPOP pattern, JSON-encoded      │  │
  │  │  data/sample_    │    │  LogEvent payloads)                        │  │
  │  │  logs/           │    │                                            │  │
  │  └────────┬─────────┘    └──────────────────┬─────────────────────────┘  │
  │           │                                  │                           │
  └───────────┼──────────────────────────────────┼───────────────────────────┘
              │  LogEvent stream                  │  LogEvent stream
              ▼                                   ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  AI Classification Pipeline                                              │
  │                                                                          │
  │  LogEvent ──► Classifier ──────────────────► ClassificationResult       │
  │                  │                                                       │
  │                  ├─ LangChainClassifier  (OpenAI / gpt-4o-mini)         │
  │                  │    LangChain prompt → structured JSON response        │
  │                  │    → validated Pydantic schema                        │
  │                  │                                                       │
  │                  └─ MockClassifier  (no API key required)                │
  │                       weighted-random severity based on log level        │
  │                       fully deterministic with fixed seed                │
  │                                                                          │
  │  IncidentPipeline: classify → build_report → persist → alert            │
  └───────────────────────────────────┬──────────────────────────────────────┘
                                      │  Incident (SQLAlchemy ORM)
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  Persistence Layer                                                       │
  │                                                                          │
  │  PostgreSQL                                                              │
  │  ┌────────────────────────────────────────────────────────────────────┐ │
  │  │ incidents table                                                     │ │
  │  │   id · source · raw_message · severity · classification            │ │
  │  │   confidence · recommended_action · summary                        │ │
  │  │   detected_at · resolved_at · created_at                           │ │
  │  └────────────────────────────────────────────────────────────────────┘ │
  └───────────────────────────────────┬──────────────────────────────────────┘
                                      │  SQLAlchemy ORM (psycopg2)
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  FastAPI REST API  (http://localhost:8000)                               │
  │                                                                          │
  │  GET  /                          welcome + endpoint index               │
  │  GET  /health                    live health check (DB + Redis + AI)     │
  │  GET  /incidents                 paginated list (filters: severity,      │
  │                                  service, resolved status)               │
  │  GET  /incidents/summary         aggregate stats, severity breakdown,    │
  │                                  MTTR, top classification                │
  │  GET  /incidents/{id}            single incident by ID                  │
  │  POST /incidents/triage          manually classify an ad-hoc log line   │
  │  POST /incidents/{id}/resolve    mark incident resolved (MTTR tracking) │
  └───────────────────────────────────┬──────────────────────────────────────┘
                                      │  HTTP (fetch / REST)
                                      ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  React Dashboard  (http://localhost:3000)                               │
  │                                                                          │
  │  ┌──────────────────────────┐  ┌───────────────────────────────────┐   │
  │  │  MTTR & Metrics          │  │  Severity Breakdown Bar Chart     │   │
  │  │  Total / Open / Resolved │  │  (Recharts, colour-coded by level) │  │
  │  │  MTTR · Top Class.       │  └───────────────────────────────────┘   │
  │  └──────────────────────────┘                                           │
  │  ┌──────────────────────────────────────────────────────────────────┐   │
  │  │  Manual Triage Panel  — paste a log message, classify on-demand  │   │
  │  └──────────────────────────────────────────────────────────────────┘   │
  │  ┌──────────────────────────────────────────────────────────────────┐   │
  │  │  Real-Time Incident Feed  (auto-refresh every 15 s)             │   │
  │  │  Severity badge · classification · summary · source · timestamp  │   │
  │  │  "Mark resolved" button updates MTTR immediately                 │   │
  │  └──────────────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
intelligent-devops-incident-management/
├── src/
│   ├── config.py                  # Pydantic-settings config (reads from .env)
│   ├── ingestion/
│   │   ├── log_reader.py          # File-based log parsing → LogEvent objects
│   │   ├── log_generator.py       # Realistic sample log file generator
│   │   └── queue_consumer.py      # Redis FIFO queue wrapper (publish / drain)
│   ├── pipeline/
│   │   ├── classifier.py          # LangChainClassifier + MockClassifier + factory
│   │   ├── schemas.py             # ClassificationResultSchema, IncidentReport
│   │   ├── reports.py             # Builds IncidentReport from event + result
│   │   ├── alerts.py              # Webhook alert dispatcher
│   │   └── runner.py              # IncidentPipeline orchestrator
│   ├── db/
│   │   ├── models.py              # SQLAlchemy ORM: Incident, Severity enum
│   │   └── session.py             # Engine, SessionLocal, init_db, session_scope
│   └── api/
│       ├── main.py                # FastAPI app factory + CORS + startup hook
│       ├── schemas.py             # Pydantic request/response models
│       ├── dependencies.py        # Shared FastAPI DI: get_db, get_pipeline
│       └── routes/
│           ├── incidents.py       # All incident endpoints + triage + resolve
│           └── health.py          # /health endpoint
├── src/dashboard/                 # React.js frontend
│   ├── src/
│   │   ├── App.js                 # Root component, data fetching, polling
│   │   ├── api.js                 # Thin fetch wrapper over the FastAPI API
│   │   └── components/
│   │       ├── IncidentFeed.js    # Scrollable real-time incident list
│   │       ├── SeverityChart.js   # Recharts bar chart (severity breakdown)
│   │       ├── MttrMetrics.js     # MTTR stat cards
│   │       ├── TriagePanel.js     # Manual triage form
│   │       └── SeverityBadge.js   # Colour-coded severity tag
│   └── package.json
├── tests/
│   ├── conftest.py                # Shared fixtures (SQLite DB, seeded MockClassifier)
│   ├── test_log_reader.py         # Log parsing unit tests (6 tests)
│   ├── test_log_generator.py      # Sample data generation tests (5 tests)
│   ├── test_classifier.py         # Classifier + factory tests (8 tests)
│   ├── test_pipeline.py           # Pipeline orchestration tests (6 tests)
│   └── test_api_incidents.py      # FastAPI endpoint tests (13 tests)
├── docker/
│   ├── api.Dockerfile             # Python FastAPI service image
│   ├── worker.Dockerfile          # Background queue-drain worker image
│   ├── dashboard.Dockerfile       # Multi-stage React build → serve
│   └── init-db.sql                # PostgreSQL bootstrap (uuid-ossp ext.)
├── scripts/
│   ├── seed_demo_data.py          # Generate logs + populate DB with incidents
│   ├── publish_sample_logs_to_redis.py  # Push log events onto the Redis queue
│   └── run_worker.py              # Continuous Redis-queue classification worker
├── .github/workflows/ci.yml       # GitHub Actions: Pytest (matrix) + Docker build
├── docker-compose.yml             # Full stack: Postgres, Redis, API, Worker, Dashboard
├── requirements.txt               # Production Python dependencies
├── requirements-dev.txt           # + Pytest, flake8, pytest-cov
├── pytest.ini
├── .env.example                   # All supported env vars with explanations
└── README.md
```

---

## Quick Start

### Option A — Docker Compose (recommended, no local Python/Node needed)

```bash
# 1. Clone
git clone https://github.com/SaiManvithReddy/intelligent-devops-incident-management.git
cd intelligent-devops-incident-management

# 2. Create a .env file from the template.
#    Leave OPENAI_API_KEY empty to use the offline MockClassifier.
cp .env.example .env

# 3. Start the full stack (Postgres + Redis + API + Worker + Dashboard)
docker compose up --build

# 4. Generate and seed demo data (in another terminal)
docker compose exec api python -m scripts.seed_demo_data

# Services:
#   REST API docs:  http://localhost:8000/docs
#   Dashboard:      http://localhost:3000
#   Health check:   http://localhost:8000/health
```

### Option B — Local Python (no Docker required for the API + pipeline)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Configure environment
cp .env.example .env
# Edit .env if needed. Minimum viable config for local demo:
#   DATABASE_URL=sqlite:///incidents.db   (SQLite - no Postgres required)
#   OPENAI_API_KEY=                       (blank → MockClassifier)

# 4. Generate sample log files
python -m src.ingestion.log_generator

# 5. Seed the database with demo incidents
python -m scripts.seed_demo_data

# 6. Start the FastAPI server
uvicorn src.api.main:app --reload --port 8000

# Interactive API docs: http://localhost:8000/docs
```

---

## Running Without an OpenAI API Key

This is the default mode. Leave `OPENAI_API_KEY` blank (or unset) in your `.env`
and the `get_classifier()` factory automatically selects `MockClassifier`.

`MockClassifier` produces severity-biased random classifications:

| Log level in source event | Probability distribution over severity outputs     |
|---------------------------|----------------------------------------------------|
| `INFO`                    | INFO 75%, WARNING 20%, CRITICAL 4%, INCIDENT 1%   |
| `WARNING`                 | INFO 15%, WARNING 55%, CRITICAL 25%, INCIDENT 5%  |
| `ERROR`                   | INFO 5%, WARNING 25%, CRITICAL 50%, INCIDENT 20%  |
| `CRITICAL`                | INFO 2%, WARNING 8%, CRITICAL 55%, INCIDENT 35%   |

The mock is fully deterministic when instantiated with a fixed seed
(`MockClassifier(seed=42)`), which is how all CI tests use it.

---

## Running the Tests

```bash
pip install -r requirements-dev.txt

# Run the full suite (38 tests, no external services required)
pytest

# With coverage report
pytest --cov=src --cov-report=term-missing

# Run a specific file
pytest tests/test_classifier.py -v
```

The test suite runs entirely offline:
- **Database**: in-memory SQLite (via SQLAlchemy `sqlite:///:memory:`)
- **Classifier**: seeded `MockClassifier` (no API calls, fully deterministic)
- **Redis**: not exercised (queue consumer tests use mock clients or skip)

---

## Example API Calls

### List recent incidents (newest first)

```bash
curl http://localhost:8000/incidents?limit=10
```

```json
{
  "total": 147,
  "limit": 10,
  "offset": 0,
  "items": [
    {
      "id": "a1b2c3d4-...",
      "source": "file:server-01.log",
      "raw_message": "Service 'postgresql' is not responding to health checks",
      "severity": "CRITICAL",
      "classification": "Service Outage Risk",
      "confidence": 0.87,
      "recommended_action": "Page the on-call engineer ...",
      "summary": "PostgreSQL on db-primary reported a critical-level event ...",
      "detected_at": "2024-01-15T10:23:45+00:00",
      "resolved_at": null,
      "is_resolved": false,
      "resolution_seconds": null
    }
  ]
}
```

### Filter by severity

```bash
curl "http://localhost:8000/incidents?severity=CRITICAL&limit=5"
```

### Get aggregate summary (dashboard data)

```bash
curl http://localhost:8000/incidents/summary
```

```json
{
  "total_incidents": 200,
  "open_incidents": 81,
  "resolved_incidents": 119,
  "severity_breakdown": [
    {"severity": "INFO",     "count": 68},
    {"severity": "WARNING",  "count": 71},
    {"severity": "CRITICAL", "count": 42},
    {"severity": "INCIDENT", "count": 19}
  ],
  "mttr_seconds": 3847.2,
  "mttr_human": "1h 4m 7s",
  "most_common_classification": "Latency Degradation",
  "generated_at": "2024-01-15T12:00:00+00:00"
}
```

### Manually triage a suspicious log line (on-demand AI classification)

```bash
curl -X POST http://localhost:8000/incidents/triage \
  -H "Content-Type: application/json" \
  -d '{
    "raw_log_line": "2024-01-15T10:23:45Z | host=db-primary | service=postgresql | level=CRITICAL | msg=Out of memory: OOM killer invoked on process postgresql",
    "persist": true
  }'
```

```json
{
  "severity": "INCIDENT",
  "classification": "Active Outage",
  "confidence": 0.94,
  "recommended_action": "Declare a major incident, assemble the incident response team ...",
  "summary": "The OOM killer has been invoked on the PostgreSQL process ...",
  "alert_sent": true,
  "incident": { "id": "e5f6...", "is_resolved": false, ... }
}
```

### Mark an incident as resolved (for MTTR tracking)

```bash
curl -X POST http://localhost:8000/incidents/e5f6.../resolve \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Health check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "environment": "development",
  "classifier": "MockClassifier",
  "database": "ok",
  "redis": "ok"
}
```

---

## Environment Variables Reference

See [`.env.example`](.env.example) for the complete list with descriptions.
Key variables:

| Variable               | Default              | Description                                                   |
|------------------------|----------------------|---------------------------------------------------------------|
| `OPENAI_API_KEY`       | *(empty)*            | Leave blank to use `MockClassifier` (no API key needed)       |
| `OPENAI_MODEL`         | `gpt-4o-mini`        | OpenAI chat model name                                        |
| `DATABASE_URL`         | *(built from parts)* | Override with `sqlite:///incidents.db` for local-only mode    |
| `POSTGRES_*`           | see `.env.example`   | Used to build `DATABASE_URL` if not set directly              |
| `REDIS_HOST`           | `localhost`          | Redis hostname (use `redis` inside Docker Compose)            |
| `ALERT_WEBHOOK_URL`    | *(empty)*            | Slack/Teams incoming webhook; blank → alert logged only       |
| `ALERT_MIN_SEVERITY`   | `CRITICAL`           | Minimum severity that triggers an alert dispatch              |
| `SAMPLE_LOG_COUNT`     | `200`                | Number of log lines generated by the sample data generator    |

---

## Demo Scripts

| Script                                          | Purpose                                                                  |
|-------------------------------------------------|--------------------------------------------------------------------------|
| `python -m src.ingestion.log_generator`         | Generate `data/sample_logs/*.log` files (realistic server log events)    |
| `python -m scripts.seed_demo_data`              | Generate logs + classify all events + seed PostgreSQL with demo incidents |
| `python -m scripts.seed_demo_data --reset`      | Wipe existing incidents and re-seed from scratch                         |
| `python -m scripts.publish_sample_logs_to_redis`| Push log events onto the Redis queue (simulates a live log shipper)       |
| `python -m scripts.run_worker`                  | Drain Redis queue continuously and run each event through the pipeline    |
| `python -m scripts.run_worker --max-batches 5`  | Drain up to 5 batch cycles, then exit (good for CI/demo)                 |

---

## CI/CD Pipeline

The [GitHub Actions workflow](.github/workflows/ci.yml) runs on every push to
`main` or `develop` and on all pull requests targeting `main`:

1. **Pytest matrix** — tests run on Python 3.11 and 3.12; 70% coverage gate.
2. **Flake8 lint** — style check with a 120-character line limit.
3. **Docker smoke tests** — builds the `api` and `worker` images; verifies the
   Python import graph resolves cleanly inside the container.

No external services (PostgreSQL, Redis, OpenAI) are used during CI — the
test suite is fully self-contained.

---

## Tech Stack

| Layer             | Technology                                           |
|-------------------|------------------------------------------------------|
| AI / LLM          | LangChain · langchain-openai · OpenAI gpt-4o-mini    |
| Backend API       | FastAPI · Uvicorn · Pydantic v2                      |
| Database          | PostgreSQL 16 (prod) · SQLite (local/CI)             |
| ORM               | SQLAlchemy 2.0                                       |
| Queue             | Redis 7 (list-based FIFO queue)                      |
| Frontend          | React 18 · Recharts                                  |
| Containerisation  | Docker · Docker Compose                              |
| Testing           | Pytest · pytest-cov · flake8                         |
| CI/CD             | GitHub Actions                                       |

---

## License

MIT
