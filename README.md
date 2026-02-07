# Obsidian Note Linker

A Python application to discover, review, and create bidirectional links between related Obsidian notes.

## Purpose

Identifies semantically and thematically related notes that should be linked, using hybrid similarity (semantic embeddings + BM25 lexical search with Reciprocal Rank Fusion). All link creation is human-in-the-loop — the application never edits notes without explicit user confirmation.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) for dependency management

## Setup

```bash
# Clone the repository
git clone <repo-url> && cd obsidian-note-linker

# Install dependencies
uv sync

# Run the application
uv run obsidian-linker
```

On first run, the web UI opens at `http://127.0.0.1:8000` and prompts you to configure your Obsidian vault path.

## Running Tests

```bash
uv run pytest -v
```

## Linting & Type Checking

```bash
uv run ruff check src/ tests/
uv run ty check
```

## Codebase Layout

```
src/obsidian_note_linker/
├── domain/                  # Pure business logic, data structures (no external deps)
│   ├── candidate.py         # CandidatePair model with scores and explanation
│   ├── config.py            # AppConfig model, path constants
│   ├── embedding_provider.py # EmbeddingProvider Protocol (swappable interface)
│   ├── markdown_stripper.py # Strip markdown formatting for embedding
│   ├── note.py              # Note model, SHA256 content hashing
│   ├── ranking.py           # RRF score computation, score-to-rank conversion
│   └── related_section_parser.py # Parse ## Related section links
├── infrastructure/          # I/O, external libraries, persistence
│   ├── bm25_index.py        # BM25 lexical index (bm25s wrapper)
│   ├── config_store.py      # Read/write ~/.config/obsidian-linker/config.json
│   ├── database.py          # SQLite engine creation (WAL mode)
│   ├── decision_store.py    # Decision CRUD (YES/NO with staleness detection)
│   ├── embedding_store.py   # Embedding CRUD (binary blob storage)
│   ├── logging_setup.py     # YAML-based logging configuration (console)
│   ├── logging.yaml         # Logging format config (5 Ws)
│   ├── model2vec_provider.py # Model2Vec embedding provider (potion-retrieval-32M)
│   ├── models.py            # SQLModel tables (NoteRecord, EmbeddingRecord, DecisionRecord)
│   ├── note_store.py        # NoteRecord CRUD
│   ├── similarity.py        # Pairwise cosine similarity (numpy)
│   └── vault_scanner.py     # Scan vault for .md files (excl. .obsidian/)
├── services/                # Orchestrate infrastructure to fulfil use cases
│   ├── candidate_service.py # Hybrid candidate generation (RRF + filtering)
│   ├── config_service.py    # Vault path validation and persistence
│   ├── indexing_service.py  # Incremental note indexing + embedding
│   └── vault_init.py        # DB + logging initialisation for a vault
├── api/                     # HTTP routing, templates, user interaction
│   ├── app.py               # FastAPI application factory
│   ├── routes/
│   │   ├── dashboard.py     # Dashboard page with indexing + candidate status
│   │   ├── indexing.py      # SSE indexing + candidate generation stream
│   │   └── settings.py      # Setup + settings pages
│   └── templates/           # Jinja2 templates (Pico.css dark mode + HTMX)
└── __main__.py              # CLI entry point (obsidian-linker command)

tests/                       # Mirrors src/ structure
├── domain/
├── infrastructure/
├── services/
└── api/
```

## Architecture

Layered architecture with strict dependency direction:

```
api/  →  services/  →  infrastructure/
                  ↘        ↓
                    domain/
```

| Layer | Responsibility | Dependencies |
|-------|----------------|--------------|
| **domain/** | Pure business logic, data structures | None (stdlib only) |
| **infrastructure/** | I/O, external libraries, persistence | domain |
| **services/** | Orchestrate infrastructure to fulfil use cases | domain, infrastructure |
| **api/** | HTTP routing, templates, user interaction | domain, services |

## State Management

| State | Location |
|-------|----------|
| App config (vault path) | `~/.config/obsidian-linker/config.json` |
| Vault state (DB, logs) | `<vault>/.obsidian-linker/` |

## Technology Stack

| Component | Choice |
|-----------|--------|
| Web framework | FastAPI |
| Templating | Jinja2 |
| Frontend interactivity | HTMX + SSE extension |
| CSS | Pico.css (dark mode only) |
| ORM | SQLModel |
| Database | SQLite (WAL mode) |
| Embeddings | model2vec (potion-retrieval-32M) |
| Lexical search | bm25s (BM25 ranking) |
| Score fusion | Reciprocal Rank Fusion (RRF) |
| Logging | Python `logging` + PyYAML |
