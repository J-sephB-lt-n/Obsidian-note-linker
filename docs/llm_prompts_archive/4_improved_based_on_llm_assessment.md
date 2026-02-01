# Obsidian Note Linker — Requirements Document

## Overview

A Python application to discover, review, and create bidirectional links between related Obsidian notes.

| Attribute | Value |
|-----------|-------|
| **Purpose** | Identify semantically/thematically related notes that should be linked |
| **Core principle** | Human-in-the-loop with maximum safety |
| **Target user** | Single user with ~189 notes, growing at ~30/month |

---

## Problem Statement

- User writes ~1 Obsidian note per day
- Many notes are semantically or thematically related but remain unlinked, especially when written far apart in time
- Consequences:
  - Obsidian graph is less useful than it should be
  - Related notes fall off radar
  - Accidental duplication of work by writing similar notes multiple times
- Manual linking has proven insufficient

---

## Functional Requirements

### FR1: Link Discovery

| ID | Requirement |
|----|-------------|
| FR1.1 | Analyze a corpus of Obsidian markdown notes |
| FR1.2 | Identify pairs of notes that are semantically/thematically related |
| FR1.3 | Assign a similarity score to each proposed pair using Reciprocal Rank Fusion (RRF) |
| FR1.4 | Use hybrid similarity: semantic embeddings (model2vec) + lexical (BM25 via bm25s) |
| FR1.5 | Similarity method must be explainable at a high level |

### FR2: Human-in-the-Loop Review

| ID | Requirement |
|----|-------------|
| FR2.1 | Provide a web-based interface for reviewing candidate pairs |
| FR2.2 | Display two candidate notes side by side with scrollable content |
| FR2.3 | Show similarity score for each pair |
| FR2.4 | Present candidates in order: random target note selection, candidates ranked by similarity to target |
| FR2.5 | Allow user to manually select a specific note to mine for candidate links |
| FR2.6 | Support three decision types per pair: **YES**, **NO**, **SKIP** |
| FR2.7 | Support session-based review (5-10 pairs per session) |

### FR2.6 Decision Semantics

| Decision | Meaning | State Change |
|----------|---------|--------------|
| **YES** | These notes should be linked | Recorded in DB; pair won't appear again; queued for linking |
| **NO** | These notes should NOT be linked | Recorded in DB; pair won't appear again |
| **SKIP** | Move to next candidate without deciding | No state change; pair may appear again in future |

### FR3: Safe Link Creation

| ID | Requirement |
|----|-------------|
| FR3.1 | By default, the application must NOT edit any note files |
| FR3.2 | Link application must be an explicit, separate action |
| FR3.3 | Show diff preview before any write operation |
| FR3.4 | Require per-note confirmation before writing |
| FR3.5 | Use atomic writes (temp file + rename) |
| FR3.6 | Maintain audit log of all file modifications |
| FR3.7 | Never overwrite existing content unexpectedly |
| FR3.8 | Create `## Related` section if missing; append links to existing section |
| FR3.9 | Prevent duplicate links (check if link already exists) |
| FR3.10 | Links must be bidirectional (both notes link to each other) |

### FR4: Incremental / Repeated Use

| ID | Requirement |
|----|-------------|
| FR4.1 | Support repeated runs over time with minimal redundant work |
| FR4.2 | Cache embeddings keyed by content hash |
| FR4.3 | Detect changed notes via SHA256 content hash |
| FR4.4 | Never show previously-decided pairs (YES or NO) again |
| FR4.5 | SKIP decisions do not persist; skipped pairs may reappear |
| FR4.6 | Inform user of indexing status (X new/modified notes need indexing) |
| FR4.7 | Allow user to trigger indexing from the UI |

### FR5: Vault Configuration

| ID | Requirement |
|----|-------------|
| FR5.1 | Application codebase is separate from the Obsidian vault |
| FR5.2 | UI must allow user to select/configure the vault path |
| FR5.3 | On first run, prompt user to select vault path |
| FR5.4 | Persist vault path selection for subsequent runs |
| FR5.5 | Allow changing vault path from the UI (e.g., settings page) |
| FR5.6 | State (`.obsidian-linker/`) is stored inside the selected vault, so state travels with vault |
| FR5.7 | Each vault has its own independent state (embeddings, decisions, audit log) |

---

## Non-Functional Requirements

### NFR1: Data Integrity and Safety (Highest Priority)

| ID | Requirement |
|----|-------------|
| NFR1.1 | Prevent accidental modification, corruption, or silent changes to notes |
| NFR1.2 | All write operations must be explicit, auditable, and verifiable |
| NFR1.3 | Git serves as the backup mechanism (no separate backup system) |
| NFR1.4 | Application state is stored in `.obsidian-linker/` inside the vault (gitignore-able, travels with vault) |
| NFR1.5 | Application config (e.g., vault path) is stored in app's config directory (e.g., `~/.config/obsidian-linker/`) |

### NFR2: Performance

| ID | Requirement |
|----|-------------|
| NFR2.1 | Indexing ~200 notes should complete in under 1 minute |
| NFR2.2 | Candidate generation should be near-instantaneous |
| NFR2.3 | Web UI should feel responsive (HTMX partial updates) |

### NFR3: Usability

| ID | Requirement |
|----|-------------|
| NFR3.1 | Single entry point (`obsidian-linker` command launches web app) |
| NFR3.2 | All actions controllable from the web UI (no separate CLI commands) |
| NFR3.3 | Markdown rendered for readability in review interface |
| NFR3.4 | Keyboard shortcuts for efficient review (optional enhancement) |
| NFR3.5 | Dark mode theme only (no light mode or theme switching) |
| NFR3.6 | Display progress bar during indexing operations |

### NFR4: Observability

| ID | Requirement |
|----|-------------|
| NFR4.1 | Use native Python `logging` module with global YAML configuration |
| NFR4.2 | Log messages must follow the 5 Ws: Who, What, When, Where, Why |
| NFR4.3 | Log file stored in `.obsidian-linker/logs/` inside the vault |
| NFR4.4 | Support configurable log levels (DEBUG, INFO, WARNING, ERROR) |

### NFR5: Extensibility

| ID | Requirement |
|----|-------------|
| NFR5.1 | Embedding provider must use a shared abstract interface (Protocol/ABC) |
| NFR5.2 | Easy to swap embedding implementations (e.g., model2vec, OpenAI, sentence-transformers) |
| NFR5.3 | Embedding provider selection configurable without code changes |

---

## Technical Design

### Architecture: Layered

```
api/  →  services/  →  infrastructure/
                  ↘        ↓
                    domain/
```

| Layer | Responsibility | Dependencies |
|-------|----------------|--------------|
| **domain/** | Pure business logic, data structures, algorithms | None (stdlib only) |
| **infrastructure/** | I/O, external libraries, persistence | domain |
| **services/** | Orchestrate infrastructure to fulfill use cases | domain, infrastructure |
| **api/** | HTTP routing, templates, user interaction | domain, services |

### Project Structure

```
obsidian-linker/
├── pyproject.toml
├── README.md
├── logging.yaml                       # Global logging configuration
├── src/
│   └── obsidian_linker/
│       ├── __init__.py
│       ├── main.py                    # Entry point
│       │
│       ├── domain/                    # Pure business logic
│       │   ├── __init__.py
│       │   ├── note.py                # Note dataclass, link parsing, hash
│       │   ├── similarity.py          # RRF algorithm, scoring logic
│       │   ├── candidate.py           # Candidate pair dataclass
│       │   └── decision.py            # Decision enum (YES/NO/SKIP)
│       │
│       ├── infrastructure/            # External systems, I/O
│       │   ├── __init__.py
│       │   ├── config.py              # App config (vault path) management
│       │   ├── database.py            # SQLModel engine, session management
│       │   ├── models.py              # DB table definitions
│       │   ├── note_reader.py         # Read markdown files from vault
│       │   ├── note_writer.py         # Safe atomic write operations
│       │   ├── embeddings/
│       │   │   ├── __init__.py        # Exports EmbeddingProvider protocol
│       │   │   ├── base.py            # EmbeddingProvider abstract interface
│       │   │   └── model2vec_provider.py  # model2vec implementation
│       │   └── lexical.py             # bm25s integration
│       │
│       ├── services/                  # Orchestration, use cases
│       │   ├── __init__.py
│       │   ├── indexing_service.py    # Detect changes, compute embeddings
│       │   ├── candidate_service.py   # Generate ranked candidates via RRF
│       │   ├── review_service.py      # Manage review sessions, record decisions
│       │   └── apply_service.py       # Preview and execute link insertion
│       │
│       └── api/                       # Web layer
│           ├── __init__.py
│           ├── app.py                 # FastAPI app, middleware, lifespan
│           ├── dependencies.py        # Dependency injection
│           ├── routes/
│           │   ├── __init__.py
│           │   ├── dashboard.py
│           │   ├── settings.py          # Vault selection, configuration
│           │   ├── indexing.py
│           │   ├── review.py
│           │   └── apply.py
│           ├── templates/
│           │   ├── base.html
│           │   ├── dashboard.html
│           │   ├── settings.html
│           │   ├── review.html
│           │   ├── apply.html
│           │   └── partials/
│           │       ├── status.html
│           │       ├── candidate.html
│           │       └── diff.html
│           └── static/
│               └── app.css
│
└── tests/
    ├── domain/
    ├── infrastructure/
    └── services/
```

### Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | User requirement |
| Dependency management | `uv` | User requirement |
| Web framework | FastAPI | Modern, async, good DX |
| Templating | Jinja2 | Standard, well-integrated |
| Frontend interactivity | HTMX | Partial updates, no build step |
| CSS | Pico.css (CDN), dark mode only | Classless, minimal effort, matches Obsidian aesthetic |
| Markdown rendering | mistune | Fast, minimal deps |
| ORM | SQLModel | Pydantic integration, FastAPI author |
| Embeddings | model2vec | Local, fast static embeddings |
| Lexical search | bm25s | Actively maintained BM25 implementation |
| Score fusion | Reciprocal Rank Fusion | Robust to scale differences |
| Database | SQLite | Single file, simple |
| Logging | Python `logging` + PyYAML | Native, configurable via YAML, 5 Ws format |

### Dependencies (pyproject.toml)

```toml
[project]
name = "obsidian-linker"
requires-python = ">=3.11"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
    "model2vec",
    "bm25s",
    "mistune",
    "sqlmodel",
    "numpy",
    "pyyaml",  # Logging configuration
]
```

### State Management

| State | Storage | Location |
|-------|---------|----------|
| **App config** (vault path) | JSON or TOML | `~/.config/obsidian-linker/config.json` |
| Note metadata | SQLite | `<vault>/.obsidian-linker/state.db` |
| Embeddings | SQLite | `<vault>/.obsidian-linker/state.db` |
| Lexical index | In-memory | Rebuilt on startup |
| Review decisions | SQLite | `<vault>/.obsidian-linker/state.db` |
| Audit log | SQLite | `<vault>/.obsidian-linker/state.db` |
| Application logs | File | `<vault>/.obsidian-linker/logs/` |

**Vault state location:** `.obsidian-linker/state.db` inside the selected vault (gitignore-able, travels with vault)

**App config location:** `~/.config/obsidian-linker/config.json` (persists vault path selection)

**Change detection:** SHA256 content hash (not mtime)

### Similarity Algorithm

1. **Semantic similarity:** Embed all notes with model2vec, compute cosine similarity
2. **Lexical similarity:** Index all notes with bm25s, compute BM25 scores
3. **Rank fusion:** For each candidate pair, compute RRF score:
   ```
   RRF(d) = 1/(k + semantic_rank) + 1/(k + lexical_rank)
   ```
   where k = 60 (standard RRF constant)
4. **Ranking:** Sort candidates by RRF score descending

### Link Format

Links are inserted into a `## Related` section using Obsidian markdown format:

```markdown
## Related

- [Note Title](<Note%20Title.md>)
```

Both notes in a pair receive links to each other (bidirectional).

---

## Scope

### In Scope

- Discover related note pairs via hybrid similarity
- Human review with YES/NO/SKIP decisions
- Safe, auditable link insertion with confirmation
- Incremental processing for repeated use
- Single-vault, local-only operation

### Out of Scope (Non-Goals)

| Non-Goal | Rationale |
|----------|-----------|
| Suggest merging duplicate notes | Different problem |
| Edit note content beyond links | Safety constraint |
| Mobile/sync support | Local-only tool |
| Non-markdown files | Obsidian notes are markdown |
| Real-time watch mode | On-demand is sufficient |
| Multi-vault support | Complexity not justified |
| Tag suggestions | Different feature |

---

## User Workflow

### First Run
1. **Launch:** Run `obsidian-linker` → opens web app in browser
2. **Configure vault:** Prompted to select Obsidian vault path (folder picker or text input)
3. **Vault saved:** Path persisted to `~/.config/obsidian-linker/config.json`

### Subsequent Runs
1. **Launch:** Run `obsidian-linker` → opens web app in browser (uses saved vault path)
2. **Dashboard:** See status (X notes need indexing, Y candidates, Z pending links)
3. **Index:** Click "Index Now" to process new/changed notes
4. **Review:** Start review session → see side-by-side comparison → YES/NO/SKIP
5. **Apply:** Preview diffs → confirm per-note → links inserted

### Changing Vault
- Access settings from dashboard to select a different vault path
- Each vault maintains its own independent state

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Corrupted note during write | Atomic writes (temp + rename) |
| Link in wrong location | Only append to `## Related` section |
| Duplicate links | Check before insert |
| Lost review decisions | SQLite with WAL mode |
| App crash mid-apply | Process one note at a time; audit log enables recovery |
| Note renamed between runs | Track by content hash, not just path |

---

## Success Criteria

1. User can identify related notes they would have missed manually
2. Review process is efficient (< 30 seconds per pair decision)
3. Zero unintended modifications to notes
4. State persists correctly across sessions
5. Changed notes are detected and re-indexed automatically
