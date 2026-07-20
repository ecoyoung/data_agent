# Data Detector

Data Detector is a FastAPI-based Feishu data assistant for Amazon business analytics. Users ask questions in Feishu with natural language; the service links the question to the structured Amazon intermediate catalog, generates read-only PostgreSQL SQL, executes it with safety checks, and replies with a Feishu card, table, and chart.

The current primary data source is the `intermediate_amazon_` table/view family, covering multiple brands, stores, markets, and report domains.

## Architecture

```text
Feishu user
  -> Feishu encrypted webhook
  -> FastAPI /feishu/webhook
  -> message idempotency + session routing
  -> deterministic brand/scope alias resolution
  -> clarification / intent detection
  -> progressive disclosure catalog loading
  -> LLM SQL generation
  -> SQL repair + safety checker + business checker
  -> read-only PostgreSQL execution
  -> chart/table/card rendering
  -> query log + feedback loop
```

Key runtime layers:

- `src/data_agent/feishu/`: Feishu webhook handling, card building, and message sending.
- `src/data_agent/agent/`: LLM client, prompt builder, intent detection, SQL repair, SQL checker, SQL executor, and few-shot retrieval.
- `src/data_agent/data_catalog/`: machine-readable catalog, metric rules, table metadata, AI_HINT family rules, join relationships, templates, and semantic routing index.
- `src/data_agent/session/`: in-memory session history plus SQLite query/feedback logs.
- `src/data_agent/visualization/`: chart rendering and Feishu-friendly table formatting.

## Progressive Disclosure

The prompt is built in layers instead of dumping the whole schema:

1. Deterministic brand/scope alias resolution, e.g. `BKN US` -> Beekeeper US scope.
2. Intent detection: trend, ranking, comparison, detail, summary, or auto.
3. Structured rules: business defaults, ask-user rules, forbidden SQL rules.
4. Table routing: keyword score, scope aliases, and lightweight semantic index.
5. Optional LLM table refinement for wide candidate pools.
6. Column pruning from `tables_columns.json`.
7. Conditional relationships, templates, and few-shot examples.

See [docs/progressive_disclosure.md](docs/progressive_disclosure.md) for the full design.

## Safety

SQL execution is guarded by:

- read-only PostgreSQL connection settings;
- statement timeout and max returned rows;
- write keyword blocking;
- single-statement SELECT/WITH enforcement;
- Catalog table allowlist;
- column existence checks;
- business rules such as required date filters, metric defaults, and forbidden aggregation patterns;
- deterministic SQL repair for known safe rewrites such as `ROUND(..., n)::numeric`, monthly `GROUP BY 1`, and text date casts.

## Concurrency

The service is designed for a single-container MVP:

- Feishu duplicate message delivery is persisted and deduplicated by message id.
- Slow LLM/SQL/card work runs in a threadpool instead of blocking the async webhook.
- Per-session queries are serialized to avoid history races.
- Global query concurrency is bounded by `MAX_CONCURRENT_QUERIES`.

See [docs/concurrency_architecture.md](docs/concurrency_architecture.md).

## Repository Layout

```text
.
├── src/data_agent/              # application package
│   ├── main.py                  # FastAPI app and health endpoint
│   ├── config.py                # settings and env loading
│   ├── agent/                   # LLM, prompt, SQL repair/check/execute
│   ├── data_catalog/            # Amazon intermediate catalog and rules
│   ├── feishu/                  # webhook, cards, sender APIs
│   ├── session/                 # history and query/feedback logs
│   └── visualization/           # charts and table formatting
├── tests/                       # automated tests
├── scripts/                     # catalog, regression, metrics, maintenance
├── evals/                       # business SQL regression cases
├── docs/                        # architecture and data catalog docs
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml
```

## Configuration

Copy `.env.example` to `.env` and fill in the Feishu, LLM, PostgreSQL, and Cloudflare values.

Important settings:

- `DEEPSEEK_API_KEY`
- `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`
- `SQL_TIMEOUT`
- `MAX_ROWS`
- `MAX_CONCURRENT_QUERIES`
- `QUERY_LOG_DB_PATH`

Do not commit `.env`, `postgresql.env`, or `storage/`.

## Run Locally

```bash
PYTHONPATH=src .venv/bin/python -m uvicorn data_agent.main:app --host 0.0.0.0 --port 8000
```

## Run With Docker

```bash
docker compose up -d --build data-agent
curl http://127.0.0.1:8010/health
```

When `.env` values change, recreate the container so Docker reloads the `env_file` values:

```bash
docker compose up -d --force-recreate data-agent
```

## Validation

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_business_sql_cases.py --execute
```

Catalog maintenance:

```bash
.venv/bin/python scripts/build_intermediate_catalog.py
.venv/bin/python scripts/build_scope_aliases.py
.venv/bin/python scripts/build_table_semantic_index.py
.venv/bin/python scripts/validate_business_sql_cases.py --execute
```

Operational review:

```bash
.venv/bin/python scripts/metrics.py --days 7
.venv/bin/python scripts/review_feedback.py --days 7
.venv/bin/python scripts/generate_regression_candidates.py --days 7
```
