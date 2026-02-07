# Dev Notes

## Slice 1 — Project Foundation + Vault Configuration (2026-02-06)

### What was built
- Layered architecture: `domain/`, `infrastructure/`, `services/`, `api/` under `src/obsidian_note_linker/`.
- **Domain**: `AppConfig` frozen dataclass with computed properties for vault state paths.
- **Infrastructure**: JSON config file persistence, SQLite engine creation (WAL mode), YAML-based logging with 5 Ws format (console only).
- **Services**: `ConfigService` for vault path validation/persistence, `initialize_vault_state()` for DB + logging setup.
- **API**: FastAPI app factory with middleware (redirects to `/setup` when unconfigured), dashboard shell, settings page, setup page. Templates use Pico.css (CDN, dark mode) + HTMX (CDN).
- **CLI**: `obsidian-linker` entry point registered in `pyproject.toml`.

### Key design decisions
- `config_path` is injectable everywhere (no global state) — enables clean testing with `tmp_path`.
- `initialize_vault_state()` returns an `Engine` rather than storing it directly — keeps the function decoupled from FastAPI.
- Middleware-based redirect for unconfigured state — simpler than per-route dependency checks.
- `TemplateResponse(request, name, context)` parameter order used (new Starlette convention).

### Test suite
- 38 tests across all layers. All pass. `ruff check` and `ty check` clean.
- `_reset_logging` autouse fixture prevents handler leakage between tests.

### Known limitations / future work
- Dashboard status cards are placeholders (will be populated by Slice 2+).
- No SQLModel table definitions yet — DB file is created but empty.
- Pico.css and HTMX loaded from CDN (no offline support).

## Slice 2 — Note Indexing: Semantic Embeddings (2026-02-07)

### What was built
- **Domain**: `Note` frozen dataclass with relative path, content, and SHA256 content hash. `EmbeddingProvider` Protocol (runtime-checkable) for swappable embedding backends. `strip_markdown()` utility for stripping markdown formatting (frontmatter, code blocks, images, links, emphasis, etc.) and `prepare_note_for_embedding()` for prepending title + stripping.
- **Infrastructure**: `NoteRecord` and `EmbeddingRecord` SQLModel tables with unique constraints and indexes. `vault_scanner` reads `.md` files recursively (excludes `.obsidian/` and `.obsidian-linker/`). `note_store` and `embedding_store` provide CRUD operations. Embeddings stored as binary blobs (single-precision float arrays via `array` module). `Model2VecProvider` wraps `model2vec.StaticModel` with `potion-retrieval-32M` as default model.
- **Services**: `IndexingService` orchestrates incremental indexing — scans vault, diffs against stored records, checks embedding cache, embeds in batches of 50, stores results. Yields `IndexingProgress` events for progress streaming. Standalone `get_indexing_status()` for dashboard (no provider needed).
- **API**: SSE-based indexing routes (`/indexing/start`, `/indexing/stream`). Dashboard shows live vault/index stats and "Index Now" button. Progress streamed via HTMX SSE extension. Model loading is lazy (cached in `app.state`). Concurrent indexing prevented via `is_indexing` flag.

### Key design decisions
- `EmbeddingProvider` is a Protocol (not ABC) — more Pythonic, no inheritance required.
- Embeddings cached by content hash (not path) — identical content shares embeddings, even across file renames.
- Binary blob storage via `array.array('f')` — compact (4 bytes/dim), stdlib-only, no numpy dependency in persistence layer.
- Markdown stripping before embedding — removes formatting noise for cleaner retrieval signal.
- Title prepended to content — provides strong topical signal for the embedding model.
- `get_indexing_status()` is a standalone function (not a class method requiring a provider) — enables the dashboard to show status without loading the model.
- SSE streaming via raw `StreamingResponse` — no external SSE library needed. HTMX SSE extension handles client-side.
- Embedding model loaded lazily on first indexing request and cached in `app.state` — avoids slow startup.
- `vault_init.py` imports `models` module to ensure SQLModel table registration before `create_all`.

### Test suite
- 138 tests across all layers. All pass. `ruff check` and `ty check` clean.
- Model2Vec provider tests use `unittest.mock.patch` to avoid downloading real model.
- `db_engine` fixture added to root conftest (imports models, creates temp engine).
- API indexing tests use a `_FakeEmbeddingProvider` injected into `app.state`.

### Known limitations / future work
- "Candidates Found" dashboard card was a placeholder (now populated by Slice 3).
- No BM25 lexical index yet — needed for hybrid similarity in Slice 3.
- No file-based logging yet (console only).
- Embedding model is downloaded from HuggingFace on first use (requires internet).

## Slice 3 — Candidate Generation: Lexical + Hybrid Ranking (2026-02-07)

### What was built
- **Domain**: `CandidatePair` frozen dataclass with per-direction scores (semantic similarity, BM25 scores, ranks) and combined RRF score. `explanation` property for human-readable reasoning. `pair_key` property for canonical sorted pair representation. `ranking.py` with RRF formula (`1/(k+rank)` for k=60) and `ranks_from_scores()` for converting scores to 1-based dense ranks. `related_section_parser.py` to parse `## Related` sections and extract linked note paths (handles percent-encoding, subdirectories, section boundaries).
- **Infrastructure**: `DecisionRecord` SQLModel table with unique constraint on `(note_a_path, note_b_path)` for persisting YES/NO decisions with content hashes at decision time. `decision_store.py` with `save_decision()` (canonical path ordering, upsert support) and `get_valid_decisions()` (filters out stale decisions where note content has changed). `BM25Index` class wrapping `bm25s` for in-memory BM25 indexing with `get_pairwise_scores()` returning N×N score matrix (self-scores zeroed). `similarity.py` using numpy for efficient pairwise cosine similarity matrix computation. `get_all_embeddings()` added to `embedding_store.py`.
- **Services**: `CandidateService` orchestrates candidate generation — loads indexed notes and embeddings, scans vault for content, builds BM25 index, computes pairwise cosine similarity, computes per-note rankings, applies RRF, filters bidirectionally-linked pairs and valid prior decisions, sorts by RRF score descending.
- **API**: Dashboard "Candidates Found" card now shows count (greyed out with "—" until indexing has run, then shows actual count with "Pairs to review" footer). Indexing SSE stream now runs candidate generation after embedding phase and includes candidate count in completion summary. `candidate_count` stored in `app.state`.

### Key design decisions
- BM25 index built during "Index Now" (same time as semantic indexing) — not on app startup, since BM25 is only useful as part of hybrid search/candidate generation.
- Decision table built ahead of slice 4 (review UI) — `DecisionRecord` stores paths in sorted order for canonical pair representation, with content hashes for staleness detection.
- Candidate count stored in `app.state` (in-memory) — greyed out on app restart until indexing is re-run, per user preference.
- Full pairwise matrix computed (not top-k) — for ~200 notes (~20,000 pairs) this is fast (<1 second).
- RRF computed from both directions (A→B and B→A), taking the maximum — handles asymmetry in BM25 scores.
- `_safe_next()` wrapper for generator consumption via `run_in_executor` — fixes a latent bug where `StopIteration` cannot propagate through asyncio executors (converted to `RuntimeError` by Python).
- numpy used in infrastructure layer for cosine similarity (not domain) — keeps domain layer stdlib-only per architecture rule.

### Test suite
- 213 tests across all layers. All pass. `ruff check` and `ty check` clean.
- Candidate service tests use a `_setup_indexed_vault()` helper that creates files, note records, and embeddings in one call.
- Tests cover: candidate generation, RRF scoring, related section parsing, decision persistence/staleness, BM25 pairwise scoring, cosine similarity, dashboard candidate count display, candidate generation after indexing.

### Known limitations / future work
- "Pending Links" dashboard card is still a placeholder (Slice 5).
- Candidate pairs not persisted to DB — recomputed each time indexing runs, count lost on restart.
- No file-based logging yet (console only).
- BM25 index is rebuilt from scratch on each indexing run (not incremental).
