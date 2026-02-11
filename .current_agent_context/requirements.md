# Note Deletion Handling — Requirements

## Problem Statement

When a note is deleted from the Obsidian vault, the application leaves behind stale state in both the database and in-memory data structures. This causes orphaned records to accumulate, and in one case (the review route) causes an unhandled crash.

## Background

The research traced the full note-deletion lifecycle across every layer. The findings are summarised below.

### What already works

| Component | Behaviour | How |
|-----------|-----------|-----|
| **Indexing** (`indexing_service.py`) | NoteRecords for deleted notes are removed during re-indexing | `deleted_paths` computed in diffing phase, `delete_note_records()` called in storing phase |
| **Search** (`search_service.py`) | Deleted notes silently excluded from search results | `_load_corpus()` guard: `if not note_path.is_file(): continue` |
| **Apply routes** (`routes/apply.py`) | `FileNotFoundError` caught, user shown "re-index" message | try/except in `next_pair()`, `confirm_pair()`, `skip_pair()` |
| **Integrity routes** (`routes/integrity.py`) | `FileNotFoundError` caught, user shown "re-index" message | try/except in `next_pair()`, `resolve()`, `confirm()` |
| **Decision staleness** (`decision_store.py`) | Decisions for deleted notes excluded from valid decisions | `get_valid_decisions()` checks `current_hashes.get(path)` returns `None` → excluded |
| **Incomplete link detection** (`related_section_parser.py`) | Links to deleted notes ignored during detection | `get_incomplete_link_pairs()`: `if target not in notes: continue` |

### What does NOT work

| # | Gap | Severity | Location |
|---|-----|----------|----------|
| 1 | **Orphaned EmbeddingRecords** — never deleted when NoteRecord is removed. Embeddings are keyed by `content_hash` with no FK to NoteRecord. Over time, orphaned embeddings accumulate silently. | Low | `indexing_service.py`, `embedding_store.py` |
| 2 | **Orphaned DecisionRecords** — persist forever for deleted notes. No FK, no cascade, no cleanup. Correctly excluded from `get_valid_decisions()` but waste space. | Low | `decision_store.py` |
| 3 | **Review route crashes with 500** — `_render_next_pair()` calls `read_and_render_note()` which raises `FileNotFoundError`. This exception is **not caught**. If a note is deleted between indexing and the user clicking "review", the app crashes. | **High** | `api/routes/review.py` (lines 216–217) |
| 4 | **In-memory candidates go stale** — `app.state.candidates` references deleted notes between indexing runs. Stale pairs persist until the user re-indexes. | Medium | `api/routes/review.py`, `api/routes/indexing.py` |
| 5 | **`get_pending_approved_pairs()` returns pairs for deleted notes** — no file-existence check. The apply routes catch the resulting `FileNotFoundError`, so no crash, but the UX is poor (user sees an error and "re-index" message). | Low | `decision_store.py` |
| 6 | **In-memory incomplete links go stale** — `app.state.incomplete_links` may reference deleted notes. The integrity routes catch `FileNotFoundError`, so no crash, but the UX is poor. | Low | `api/routes/integrity.py` |

---

## Requirements

### R1: Clean up orphaned EmbeddingRecords during indexing

**What:** When `delete_note_records()` removes NoteRecords for deleted notes during the storing phase of `run_indexing()`, also delete any EmbeddingRecords whose `content_hash` is no longer referenced by any remaining NoteRecord.

**Why:** Prevents silent accumulation of orphaned embedding blobs in the database.

**Constraints:**
- Only delete embeddings that are truly orphaned (no NoteRecord references that `content_hash`). Two different notes with the same content would share an embedding — only delete when zero NoteRecords reference the hash.
- The cleanup must happen within the same indexing run, after NoteRecord deletion.
- Must add a function to `embedding_store.py` (e.g. `delete_orphaned_embeddings(engine)` or `delete_embeddings_by_hashes(engine, content_hashes)`) — do not inline SQL in the service.

**Acceptance criteria:**
- After indexing a vault where a note was deleted, no EmbeddingRecord exists whose `content_hash` is not referenced by at least one NoteRecord.
- If two notes shared the same content hash and only one is deleted, the embedding is preserved.

---

### R2: Clean up orphaned DecisionRecords during indexing

**What:** After NoteRecord deletion during indexing, delete any DecisionRecords where either `note_a_path` or `note_b_path` no longer corresponds to an existing NoteRecord.

**Why:** Prevents accumulation of stale decision records and avoids them appearing (and being immediately filtered out) in `get_valid_decisions()` and `get_pending_approved_pairs()`.

**Constraints:**
- Must add a function to `decision_store.py` (e.g. `delete_decisions_for_paths(engine, deleted_paths)`) — do not inline SQL in the service.
- Decisions are stored with canonical path ordering (`note_a_path < note_b_path`), so the cleanup must check both columns.
- This is a data cleanup, not a safety-critical path. A stale decision that slips through is harmless (just wasted space).

**Acceptance criteria:**
- After indexing a vault where a note was deleted, no DecisionRecord references a path that has no corresponding NoteRecord.

---

### R3: Handle `FileNotFoundError` in the review route

**What:** Wrap the `read_and_render_note()` calls in `_render_next_pair()` (in `api/routes/review.py`) with a try/except for `FileNotFoundError`. When caught:
1. Remove the stale pair from `app.state.candidates`.
2. Log a warning.
3. Advance to the next candidate (recursively call `_render_next_pair` or re-enter the loop) rather than showing an error to the user.

**Why:** This is the only route that crashes (500) when a note is deleted between indexing and review. All other routes already handle this.

**Constraints:**
- Follow the same pattern as the apply and integrity routes.
- Do not show a "re-index" error for a single stale pair — silently skip it and move on. The user should only see an error if something more fundamental is wrong.
- If ALL remaining candidates reference deleted notes, eventually the loop exhausts and the user sees the normal "target done" state.

**Acceptance criteria:**
- Deleting a note between indexing and review does not cause a 500 error.
- The stale pair is removed from `app.state.candidates`.
- The user sees the next valid candidate (or the "done" state) without interruption.

---

### R4: Handle `FileNotFoundError` in the review decide route

**What:** The `record_decision()` call in the `decide()` handler (in `api/routes/review.py`) calls `get_note_record_by_path()` which returns `None` for a deleted note, raising `ValueError`. Catch this and handle gracefully:
1. Remove the stale pair from `app.state.candidates`.
2. Log a warning.
3. Advance to the next candidate.

**Why:** If a note is deleted between displaying a review pair and the user clicking YES/NO, the decision recording fails.

**Constraints:**
- The pair should be dropped, not persisted with stale data.

**Acceptance criteria:**
- Deleting a note between seeing a review pair and clicking YES/NO does not crash.
- The stale pair is removed from `app.state.candidates`.
- The user sees the next candidate or the "done" state.

---

### R5: Improve pending pairs UX when notes are missing (optional, low priority)

**What:** In the apply route's `next_pair()` handler, when a `FileNotFoundError` is caught for a pending pair, instead of showing an error and stopping, automatically skip the broken pair and advance to the next one. Optionally mark the decision as "orphaned" so it doesn't keep reappearing.

**Why:** Currently the user sees "Note file missing — please re-index" and the flow stops. This is functional but could be smoother.

**Constraints:**
- This is a UX polish, not a bug fix. The current behaviour (error message) is acceptable.
- If implemented, must not silently discard the decision without logging.

**Acceptance criteria:**
- When a pending pair references a deleted note, the user sees the next valid pair (or "all done") without needing to re-index.

---

## Out of Scope

- **Real-time file watching** — deletion is only detected on the next indexing run. This is by design (FR: "Real-time watch mode" is in the Waiting Room).
- **Note rename detection** — tracking renames (as opposed to delete + create) is a separate concern. The current system treats a rename as a deletion of the old path and creation of a new one, which is correct.
- **Proactive in-memory cache invalidation** — we are not adding file watchers to invalidate `app.state.candidates` or `app.state.incomplete_links` in real time. The fix is to handle staleness gracefully when it's encountered.
