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

## Slice 4 — Human-in-the-Loop Review (2026-02-08)

### What was built
- **Infrastructure**: `markdown_renderer.py` wrapping mistune for markdown-to-HTML rendering. Module-level renderer instance for performance.
- **Services**: `ReviewService` orchestrating the review workflow — target listing with candidate counts, candidate filtering per target (with skip support), random target selection, decision recording (looks up content hashes from DB, delegates to `decision_store`), note reading and rendering. `ReviewTarget` frozen dataclass for target summaries.
- **API**: Review routes (`/review`, `/review/random-target`, `/review/select-target`, `/review/decide`). Search placeholder route (`/search`). Updated nav bar with Review and Search links. Dashboard "Candidates Found" card now links to review page when candidates > 0.
- **Templates**: `review.html` (full page with target selection — random button + note dropdown), `_review_pair.html` (side-by-side rendered markdown with YES/NO/SKIP buttons and explanation bar), `_review_target_done.html` (target completion with next-target options), `search.html` (placeholder). Updated `base.html` and `dashboard.html`.
- **App wiring**: `app.state.candidates` stores full candidate list after indexing (not just count). Indexing route now calls `generate_candidates()` instead of `get_candidate_count()`. Review routes registered in app factory.

### Key design decisions
- **No session size** — continuous flow per user preference. User reviews one pair at a time and exits when done.
- **Target selection on each round** — user chooses between "Random Target" and "Select a Note" before each target's review. Targets listed alphabetically with candidate counts in a `<select>` dropdown.
- **Candidates stored in `app.state.candidates`** (in-memory list) — after each YES/NO decision, the pair is removed from the list. On app restart, candidates are None and must be regenerated via indexing.
- **SKIP tracking via hidden form field** — skipped pair keys passed as comma-separated `path_a|path_b` strings in form data. Only persists for the current target session; refreshing the page resets skips.
- **Route convention matches existing pattern** — `APIRouter()` without prefix, explicit full paths (e.g. `/review`, `/review/decide`). Avoids FastAPI's trailing-slash redirect issue.
- **Side-by-side layout using Pico.css grid** — scrollable note panels with max-height 60vh. Custom CSS for decision button colors (green YES, red NO, neutral SKIP).
- **Decision recording looks up content hashes from NoteRecord table** — ensures hashes match what was indexed, enabling staleness detection.
- **Search placeholder added now** — nav bar includes Search link pointing to a "Coming Soon" page, future-proofing the navigation for Slice 7.

### Test suite
- 267 tests across all layers. All pass. `ruff check` and `ty check` clean.
- 11 tests for markdown renderer (headings, formatting, code, links, etc.)
- 22 tests for review service (target listing, candidate filtering, decisions, rendering, random target)
- 21 tests for review routes (review page states, random/select target, decide with YES/NO/SKIP, search placeholder, nav links, dashboard review link)
- 2 pre-existing dashboard tests updated ("Pairs to review" → "Review candidates")

### Known limitations / future work
- "Pending Links" dashboard card is still a placeholder (Slice 5).
- Candidate pairs stored in-memory only — lost on app restart, must re-index.
- No keyboard shortcuts for review decisions (NFR3.4 — optional enhancement).
- No file-based logging yet (console only).
- BM25 index is rebuilt from scratch on each indexing run (not incremental).

## Fix: Determinate Progress Bars During Indexing (2026-02-08)

### Problem
All progress bars during indexing showed indeterminate animation (repeated pulsing bar) instead of actual progress. Root causes:
- Scanning/diffing phases used `total=0` (indeterminate) or yielded once with `current=0` that never advanced.
- Embedding phase yielded progress at batch *start* (before work was done), not after completion. Cached embeddings were invisible in the progress.
- Storing phase yielded `current=0` once and never updated during the upsert loop.
- Candidate generation showed a single indeterminate bar with no sub-step reporting.

### What was changed
- **Domain**: Added `ProgressUpdate` frozen dataclass in `domain/progress.py` — generic progress type shared by indexing and candidate services.
- **`IndexingProgress`** now inherits from `ProgressUpdate` (adds `result` field only).
- **`IndexingService.run_indexing()`** — fixed all phases:
  - **Scanning**: yields `(0,1)` start → `(1,1)` done with note count.
  - **Diffing**: yields `(0,1)` start → `(1,1)` done with diff summary.
  - **Embedding**: total = all notes to embed (cached + uncached). Cached embeddings advance progress immediately. Uncached batches yield AFTER completion, not before. Phase skipped entirely when nothing to embed.
  - **Storing**: yields per-note progress during upserts + batch progress for deletions. Phase skipped when nothing to store.
- **`CandidateService`** — added `generate_candidates_with_progress()` generator method yielding `ProgressUpdate` events across 4 sub-steps (load data, build BM25 index, compute similarity, rank+filter). Original `generate_candidates()` now wraps this.
- **Indexing route** — candidate generation section consumes the progress generator with SSE streaming (same pattern as indexing). `_render_progress()` now accepts `ProgressUpdate` (parent type).

### Key design decisions
- **`ProgressUpdate` in domain layer** — generic, reusable type with no external deps. Services that need progress reporting use it directly; `IndexingProgress` extends it only to add the `result` field.
- **Phases skipped when nothing to do** — no misleading 0% bars for empty work. If nothing changed, only scanning and diffing phases appear (both reach 100%).
- **Cached embeddings reflected in progress** — user sees the bar jump forward proportionally to cache hits, then advance through remaining uncached batches.
- **`generate_candidates_with_progress()` as generator** — follows the same pattern as `run_indexing()`. Original `generate_candidates()` preserved for backward compatibility.

### Test suite
- 287 tests across all layers. All pass. `ruff check` and `ty check` clean.
- 12 new indexing service tests: scanning/diffing yield determinate (0/1→1/1), embedding advances per batch, embedding accounts for cache, all-cached completion, storing per-note progress, storing includes deletions, skipped phases, all phases reach completion, monotonically non-decreasing progress.
- 7 new candidate service tests: yields events, reaches completion, uses "candidates" phase, monotonically non-decreasing, stores results, fewer-than-2 notes, backward compat.
- 2 new route tests: candidate progress events in SSE, determinate progress bars in stream.

## Slice 5 — Safe Link Creation (2026-02-08)

### What was built
- **Domain**: `link_builder.py` with `format_obsidian_link()` (Obsidian markdown link format with percent-encoding), `insert_links_into_content()` (creates/appends `## Related` section, duplicate prevention via `related_section_parser`), and `compute_content_diff()` (unified diff for preview).
- **Infrastructure**: `AuditRecord` SQLModel table for logging all file modifications (FR3.6). `audit_store.py` with `save_audit_entry()` and `get_audit_log()`. `file_writer.py` with `atomic_write()` using temp-file-then-rename (FR3.5). `applied_at` nullable datetime added to `DecisionRecord` for tracking applied decisions. `decision_store.py` extended with `get_pending_approved_pairs()` (unapplied YES decisions) and `mark_decision_applied()`. DB migration in `database.py` to add `applied_at` column to existing databases.
- **Services**: `LinkService` orchestrating the full link-application workflow — `get_pending_pairs()`, `preview_pair()` (generates `PairDiffPreview` with unified diffs for both notes), and `apply_pair()` (reads notes, inserts links, writes atomically, creates audit entries, marks decision as applied). Only writes notes that actually change (skips if link already exists).
- **API**: Apply routes (`/apply`, `/apply/next-pair`, `/apply/confirm`, `/apply/skip`). Templates: `apply.html` (landing page with pending count + "Begin" button), `_apply_pair.html` (side-by-side diff preview with syntax-coloured unified diff, Apply/Skip buttons), `_apply_done.html` (completion/error partial). "Apply" added to nav bar in `base.html`. "Pending Links" card added to dashboard with live count from DB. Dashboard route updated to query `get_pending_approved_pairs()`.

### Key design decisions
- **`applied_at` on `DecisionRecord`** — simplest approach to track which YES decisions have been applied. Nullable (None = not yet applied). Avoids a separate tracking table.
- **DB migration via `_run_migrations()` in `database.py`** — idempotent ALTER TABLE guarded by column existence check, safe to run on every startup. Handles existing databases that lack the `applied_at` column.
- **Pair-by-pair UX** — user reviews one pair at a time with diff preview, then confirms or skips. Applied pairs are immediately marked, so re-loading the page shows accurate remaining count.
- **Skip during apply is transient** — skipping a pair during the apply flow just moves to the next pair. The skipped pair remains pending and will reappear on the next visit.
- **No-op detection** — if both notes already have the required links (e.g. manually added), `insert_links_into_content` returns unchanged content, no file write occurs, and no audit entry is created. The decision is still marked as applied.
- **Diff preview uses `difflib.unified_diff`** — stdlib, no dependencies. Template renders with CSS syntax colouring (green for additions, red for removals, blue for headers, purple for hunk markers).
- **Atomic writes via `tempfile.mkstemp` + `Path.rename`** — temp file created in same directory as target (same filesystem), ensuring atomic rename on POSIX.
- **Audit log records content hashes before and after** — enables verification that the expected change was applied.

### Test suite
- 359 tests across all layers. All pass. `ruff check` and `ty check` clean.
- 20 domain tests: link formatting (simple, spaces, subdirectory, special chars), content insertion (create section, append, duplicate prevention, multiple links, before next heading, preserves content), diff computation (added lines, filename header, empty diff, context).
- 8 audit store tests: save entry, timestamp, multiple entries, filter by note, all entries, ordering.
- 9 new decision store tests: pending approved pairs (returns unapplied YES, excludes NO, excludes applied, empty, multiple), mark applied (marks, reversed order, timestamp, nonexistent).
- 6 file writer tests: writes content, creates file, preserves on failure, no temp files left, UTF-8, nested path.
- 14 link service tests: get pending pairs, preview diffs (both notes, link content, already exists, titles), apply (writes files, creates section, marks applied, audit entries, no duplicates, no-op skips write, spaces in paths, missing file).
- 15 apply route tests: page states (configured, no pending, count, start button), next pair (diff preview, titles, done), confirm (applies + shows next, writes to disk, done after last), skip (doesn't apply), nav link, dashboard pending links card (count, zero, link to apply).

## Slice 6 — Link Integrity (2026-02-09)

### What was built
- **Domain**: `IncompleteLink` frozen dataclass in `related_section_parser.py` — represents a one-directional link where source links to target but target doesn't link back. `get_incomplete_link_pairs()` function detects all such pairs from a notes dict, excluding links to non-existent notes, returning results sorted by (source, target). `remove_link_from_content()` in `link_builder.py` — removes a specific link from a `## Related` section, removing the entire section heading if it becomes empty.
- **Services**: `IntegrityService` in `integrity_service.py` — orchestrates resolution of incomplete links. `preview_complete()` and `preview_remove()` generate `ResolutionPreview` dataclasses with unified diffs. `apply_complete()` adds the missing reverse link to the target note. `apply_remove()` deletes the one-way link from the source note. Both apply methods use atomic writes and create audit entries (`COMPLETE_LINK` / `REMOVE_LINK`). Standalone `detect_incomplete_links(vault_path)` function scans the vault and returns all incomplete links.
- **API**: Integrity routes (`/integrity`, `/integrity/next-pair`, `/integrity/resolve`, `/integrity/confirm`). Templates: `integrity.html` (landing page with count and "Begin" button), `_integrity_pair.html` (side-by-side rendered markdown with Complete/Remove buttons and explanation), `_integrity_preview.html` (diff preview with syntax-coloured unified diff and Confirm button), `_integrity_done.html` (completion/error partial). "Integrity" added to nav bar in `base.html`. "Incomplete Links" card added to dashboard with live count.
- **Indexing integration**: Incomplete link detection runs as a new phase after candidate generation during the indexing SSE stream. Results stored in `app.state.incomplete_links` and `app.state.incomplete_link_count`. Progress events streamed with phase name "integrity". Completion summary includes incomplete link count.

### Key design decisions
- **Detection after indexing** — incomplete links are detected by scanning the vault during the indexing pipeline, stored in `app.state`. Like candidates, the count is `None` (greyed-out dash on dashboard) until indexing has been run. This avoids stale data since the vault is freshly scanned.
- **Two-step resolution UX** — pair-by-pair flow where the user first sees both notes side-by-side (rendered markdown) to inform their decision, then chooses Complete or Remove, sees a diff preview, and confirms. This mirrors the Apply flow but with an extra choice step.
- **No "ignore" option** — per FR6.3, all incomplete links must be resolved by either completing or removing. There is no skip/ignore option.
- **Single-note modification per action** — completing modifies only the target note (adds reverse link), removing modifies only the source note (deletes one-way link). This simplifies the diff preview and audit trail.
- **`IncompleteLink` in domain layer** — placed in `related_section_parser.py` alongside the detection logic since it's a pure domain concept derived from note content parsing.
- **`remove_link_from_content()` removes empty sections** — if removing the last link from a `## Related` section, the heading itself is also removed to avoid leaving empty sections.
- **Resolved links removed from `app.state`** — after confirming a resolution, the link is removed from the in-memory list and count is updated. This provides instant feedback without requiring re-indexing.

### Test suite
- 423 tests across all layers. All pass. `ruff check` and `ty check` clean.
- 10 domain tests for `get_incomplete_link_pairs`: one-directional detection, bidirectional exclusion, empty notes, non-existent targets, multiple incomplete, mixed complete/incomplete, sorting, percent-encoded paths, subdirectories.
- 8 domain tests for `remove_link_from_content`: removes target link, removes section when empty, unchanged if not found, unchanged if no section, percent-encoded, subdirectory, preserves surrounding content, preserves next heading.
- 18 service tests: detection (4), preview complete (3), preview remove (2), apply complete (4), apply remove (5).
- 24 route tests: integrity page (5 states), next pair (4), resolve (3 diff previews), confirm (6 including disk writes, state updates, audit entries), navigation (1), dashboard card (5).
- 4 indexing integration tests: stores count in app state, completion summary mentions incomplete links, integrity progress events in stream, detects actual incomplete links in vault.

### Known limitations / future work
- No file-based logging yet (console only).
- BM25 index is rebuilt from scratch on each indexing run (not incremental).
- Candidate pairs and incomplete links stored in-memory only — lost on app restart, must re-index.

## Slice 7 — Document Search (2026-02-09)

### What was built
- **Domain**: `SearchMode` enum (FTS, SEMANTIC, HYBRID) and `SearchResult` frozen dataclass in `domain/search.py`. `generate_snippet()` utility that strips markdown and truncates at word boundaries with ellipsis.
- **Infrastructure**: `BM25Index.query()` method for single-query retrieval (top-k results with scores). `BM25Index.query_all_scores()` for full-corpus scoring (needed for hybrid RRF combination). `compute_query_cosine_similarity()` in `similarity.py` for computing cosine similarity between a single query embedding and all corpus embeddings.
- **Services**: `SearchService` orchestrating all three search modes — FTS (BM25 lexical), semantic (embedding cosine similarity), and hybrid (RRF fusion of both). Includes `check_readiness()` for FR7.9 index status warnings. BM25 index built lazily from vault notes on each search (not cached in `app.state` — decoupled from indexing pipeline). `_CorpusEntry` internal model and `_display_title()` utility for filename-to-title conversion.
- **API**: Three routes — `GET /search` (full page with query input and mode selector), `GET /search/results` (HTMX partial for results list), `GET /search/note` (HTMX partial for inline note expansion). Mode defaults to Hybrid per FR7.5.
- **Templates**: `search.html` (full page with search form, radio-button mode selector, HTMX results area), `_search_results.html` (results partial with title, score, snippet, view button; warning display; zero-results handling), `_search_note.html` (inline expanded note with rendered markdown, scrollable content, close button).

### Key design decisions
- **BM25 index built per-search, not cached in `app.state`** — decouples search from the indexing pipeline. Search works after app restart as long as notes are indexed in DB (just reads vault files to build BM25). For ~200 notes, BM25 build is <100ms so this is fine for NFR2.4 (<1 second response).
- **Separate `query()` and `query_all_scores()` on BM25Index** — `query()` returns sorted top-k results (used by FTS mode), `query_all_scores()` returns scores in corpus order for all documents (needed by hybrid mode to convert to ranks for RRF).
- **`compute_query_cosine_similarity()` in infrastructure** — numpy-based, mirrors the pairwise function but for a single query vector against a corpus. Returns scores in corpus order for rank conversion.
- **Hybrid search uses same RRF approach as candidate generation** — `ranks_from_scores()` converts BM25 and semantic scores to 1-based dense ranks, then `compute_rrf_score()` combines them. Consistent algorithm across the application.
- **Inline note expansion using `<details>` + HTMX** — user clicks "View full note" to expand the result in-place. HTMX loads rendered content lazily on first click (`hx-trigger="click once"`). Close button collapses the `<details>` element. Stays on the search page for easy multi-result browsing.
- **Zero-score results excluded from FTS** — BM25 returns 0.0 for documents with no matching terms. These are filtered out to avoid showing irrelevant results.
- **Warning system for FR7.9** — `SearchService.check_readiness()` checks for: no indexed notes, no embeddings, or missing embedding provider. Returns a human-readable warning message that the route renders in the results area.
- **`_display_title()` converts filename stems to titles** — replaces hyphens/underscores with spaces and applies title-casing (e.g. `"machine-learning"` → `"Machine Learning"`).
- **Old placeholder test updated** — `TestSearchPlaceholder.test_search_page_shows_coming_soon` replaced with `TestSearchPage.test_search_page_renders_search_form` since the page is now fully implemented.

### Test suite
- 501 tests across all layers. All pass. `ruff check` and `ty check` clean.
- 14 domain tests: SearchMode enum values and string conversion, SearchResult creation and immutability, snippet generation (short content, truncation, word boundaries, markdown stripping, frontmatter, empty, default length, exact boundary).
- 9 BM25 query tests: returns results, index-score tuples, relevant doc first, non-negative scores, top-k limiting, top-k larger than corpus, sorted by score, query_all_scores count, query_all_scores relevance.
- 6 similarity query tests: identical vectors, orthogonal, multiple corpus, valid range, known value, empty corpus.
- 28 search service tests: FTS (10 — returns results, types, relevance ranking, scores, sorting, snippets, titles, no provider needed, top-k, zero-score exclusion), semantic (4 — returns results, sorting, requires provider, top-k), hybrid (4 — returns results, sorting, requires provider, top-k), edge cases (10 — empty query, whitespace, no indexed notes, readiness checks for all modes with/without provider, relative paths, subdirectories).
- 21 search route tests: search page (5 — renders, query input, mode selector, default hybrid, navigation), search results (12 — FTS/semantic/hybrid, title/score/snippet/count, empty query, no matches, index warning, provider warning, view button), note view (4 — renders content, title, not found, close mechanism).

### Known limitations / future work
- No file-based logging yet (console only).
- BM25 index is rebuilt from scratch on each search (not cached). For current vault size (~200 notes) this is fine, but for larger vaults a cached index would improve performance.
- Candidate pairs and incomplete links stored in-memory only — lost on app restart, must re-index.
- Snippet is always the first ~200 characters of stripped content — could be improved to show the most relevant passage matching the query.
