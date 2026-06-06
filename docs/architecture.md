# Architecture Notes

## Component Responsibilities

### Log Ingestion (`src/ingestion/`)

Two complementary ingestion paths exist:

1. **File-based** (`log_reader.py`): reads structured `.log` files produced by
   the sample generator or a real log shipper. The `tail_log_directory` helper
   processes all files in sorted order, making batch ingestion deterministic and
   testable.

2. **Queue-based** (`queue_consumer.py`): `RedisLogQueue` wraps a Redis list as
   a FIFO queue. Producers call `publish()` / `publish_many()`; the background
   worker drains via `drain()` / `consume()`. This is the path used in the
   "production-shaped" Docker Compose stack.

Both paths normalize raw input to `LogEvent` dataclasses.

### AI Classification Pipeline (`src/pipeline/`)

The `Classifier` protocol (structural typing via `@runtime_checkable`) lets the
two concrete implementations (`LangChainClassifier` and `MockClassifier`) be
interchanged transparently. The single factory function `get_classifier()` is the
right way to obtain a classifier - it reads `OPENAI_API_KEY` from configuration
and selects the appropriate backend automatically.

`LangChainClassifier` uses a structured-output approach: the system prompt
instructs the model to respond with a JSON-only payload, and the response is
validated against a Pydantic schema before returning a `ClassificationResult`. On
any failure (bad JSON, schema mismatch, network error, rate limit), it silently
falls back to `MockClassifier` for that single event rather than crashing the
pipeline.

### Persistence Layer (`src/db/`)

`Incident` is the only ORM model. `Severity` is stored as a native-enum-free
VARCHAR column (`Enum(..., native_enum=False)`) so the same model works against
both PostgreSQL (production) and SQLite (CI/local dev). `init_db()` is
idempotent — safe to call at every API startup.

### Alerting (`src/pipeline/alerts.py`)

`AlertDispatcher` implements a simple severity threshold gate: only incidents
at or above `ALERT_MIN_SEVERITY` (default `CRITICAL`) trigger a dispatch. When
`ALERT_WEBHOOK_URL` is blank (the default), alerts are logged locally and
recorded in `sent_alerts` for testing/introspection but no HTTP call is made.
This keeps the full stack runnable without Slack or any webhook target.

## Design Decisions

- **`lru_cache` on `get_settings()` and `get_pipeline()`**: Settings and the
  AI classifier backend are expensive to construct (the LangChain client
  validates the API key on first use). Caching them at the process level avoids
  per-request overhead without needing a global `startup` hook.

- **SQLite for tests**: `sqlite:///:memory:` eliminates the PostgreSQL dependency
  from the CI matrix entirely. The ORM uses standard SQL-92 features and
  `native_enum=False`, so the same model works across both backends with no
  conditional code.

- **Seeded `MockClassifier` in tests**: Using `MockClassifier(seed=N)` makes
  test assertions about classification results deterministic, even across Python
  version upgrades. Each test that needs predictable output instantiates its
  own seeded instance rather than relying on shared state.

- **`IncidentPipeline.process_event` accepts an optional `db` parameter**:
  This lets callers (API route handlers, test fixtures, standalone scripts) opt
  in to persistence without coupling the pipeline to a live database connection.
  When `db=None`, the pipeline classifies, alerts, and returns — but writes
  nothing to disk.
