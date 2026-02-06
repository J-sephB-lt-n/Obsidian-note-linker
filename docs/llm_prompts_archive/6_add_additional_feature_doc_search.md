# Obsidian Note Linker — Refined Requirements Document

## Overview

A Python application to discover, review, and create bidirectional links between related Obsidian notes.

| Attribute | Value |
|-----------|-------|
| **Purpose** | Identify semantically/thematically related notes that should be linked |
| **Core principle** | Human-in-the-loop with maximum safety |
| **Target user** | Single user with ~189 notes, growing at ~30/month |

---

## 1) Project Needs (Project Drivers)

### 1.1 The Purpose of the Project

| Attribute | Value |
|-----------|-------|
| **Business Problem** | User writes ~1 Obsidian note per day, but many semantically/thematically related notes remain unlinked, especially when written far apart in time |
| **Consequences** | (1) Obsidian graph is less useful, (2) Related notes fall off radar, (3) Accidental duplication of work |
| **Why Solution Matters** | Manual linking has proven insufficient; automation with human oversight can surface connections the user would otherwise miss |

### 1.2 Stakeholders

| Stakeholder | Role |
|-------------|------|
| **User** | Single developer with ~189 notes, growing at ~30/month; sole user of the tool |

### 1.3 Relevant Facts and Assumptions

| Type | Description |
|------|-------------|
| **Fact** | Notes are stored as markdown files in an Obsidian vault |
| **Fact** | Vault is version-controlled with Git (serves as backup) |
| **Assumption** | User has Python 3.12+ and `uv` installed |
| **Assumption** | Single-user, local-only usage (no sync, no multi-user) |

---

## 2) Project Requirements

### 2a) Project Constraints

| Constraint Type | Description |
|-----------------|-------------|
| **Technology** | Python 3.12+, `uv` for dependency management |
| **Technology** | Local-only operation (no cloud services for core functionality) |
| **Extensibility** | Embedding provider must use a shared abstract interface (Protocol/ABC) to allow swapping implementations (model2vec, OpenAI, sentence-transformers, etc.) |
| **Safety** | Human-in-the-loop: application must never edit notes without explicit user confirmation |
| **Codebase** | Application codebase is separate from the Obsidian vault |
| **State** | Vault-specific state stored inside vault (`.obsidian-linker/`); app config stored in user home (`~/.config/obsidian-linker/`) |

| Naming Convention | Description |
|-------------------|-------------|
| **Link format** | Obsidian markdown: `- [Note Title](<Note%20Title.md>)` |
| **Related section** | Links inserted into `## Related` section |

---

### 2b) Functional Requirements

#### Scope of the Work

| Boundary | Description |
|----------|-------------|
| **Business area** | Personal knowledge management — specifically, discovering and creating links between related Obsidian notes |
| **Problem boundary** | Unlinked related notes in a single Obsidian vault |

#### Scope of the Product

| In Scope | Out of Scope |
|----------|--------------|
| Discover related note pairs via hybrid similarity | Suggest merging duplicate notes |
| Human review with YES/NO/SKIP decisions | Edit note content beyond links |
| Safe, auditable link insertion with confirmation | Mobile/sync support |
| Incremental processing for repeated use | Non-markdown files |
| Single-vault, local-only operation | Real-time watch mode |
| Search across all notes (FTS, semantic, hybrid) | Multi-vault support |
| | Tag suggestions |

#### Atomic Functional Requirements

**FR1: Link Discovery**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR1.1 | Analyze a corpus of Obsidian markdown notes | All `.md` files in vault (excl. `.obsidian/`) are parsed |
| FR1.2 | Identify pairs of notes that are semantically/thematically related | Candidate pairs generated with similarity > threshold |
| FR1.3 | Assign a similarity score using Reciprocal Rank Fusion (RRF) | Each pair has a numeric RRF score |
| FR1.4 | Use hybrid similarity: semantic embeddings + lexical (BM25) | Both methods contribute to final ranking |
| FR1.5 | Each candidate pair must include an explanation of why it was suggested | Semantic: similarity score displayed. Lexical: matching terms shown if feasible, otherwise BM25 score. Combined RRF score displayed. |
| FR1.6 | Exclude note pairs that already have bidirectional links in their `## Related` sections | Only pairs lacking mutual `## Related` links are suggested |

**FR2: Human-in-the-Loop Review**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR2.1 | Provide a web-based interface for reviewing candidate pairs | Web UI accessible at localhost |
| FR2.2 | Display two candidate notes side by side with scrollable content | Both notes visible simultaneously |
| FR2.3 | Show similarity score for each pair | Score displayed in UI |
| FR2.4 | Present candidates in order: random target, candidates ranked by similarity | Ordering matches specification |
| FR2.5 | Allow user to manually select a specific note to mine for candidate links | Note selection available in UI |
| FR2.6 | Support three decision types: YES, NO, SKIP | All three buttons functional |
| FR2.7 | Support session-based review (5-10 pairs per session) | Session ends after configured number |

**FR2.6 Decision Semantics**

| Decision | Meaning | State Change | Reconsideration |
|----------|---------|--------------|-----------------|
| **YES** | These notes should be linked | Recorded in DB; queued for linking | If either note modified, pair reappears for review |
| **NO** | These notes should NOT be linked | Recorded in DB | If either note modified, pair reappears for review |
| **SKIP** | Move to next candidate without deciding | No state change | Pair may reappear anytime |

**FR3: Safe Link Creation**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR3.1 | By default, application must NOT edit any note files | No writes without explicit action |
| FR3.2 | Link application must be an explicit, separate action | Separate "Apply" step in workflow |
| FR3.3 | Show diff preview before any write operation | Diff displayed in UI |
| FR3.4 | Require per-note confirmation before writing | Confirm button per note |
| FR3.5 | Use atomic writes (temp file + rename) | Write operation is atomic |
| FR3.6 | Maintain audit log of all file modifications | All writes logged to DB |
| FR3.7 | Never overwrite existing content unexpectedly | Only append to `## Related` section |
| FR3.8 | Create `## Related` section if missing; append links to existing section | Section created/appended correctly |
| FR3.9 | Prevent duplicate links | Existing links checked before insert |
| FR3.10 | Links must be bidirectional | Both notes receive links to each other |

**FR4: Incremental / Repeated Use**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR4.1 | Support repeated runs with minimal redundant work | Only changed notes re-indexed |
| FR4.2 | Cache embeddings keyed by content hash | Embeddings stored in DB |
| FR4.3 | Detect changed notes via SHA256 content hash | Hash comparison used |
| FR4.4 | Never show previously-decided pairs (YES or NO) again unless either note has been modified since the decision | Decided pairs filtered out; modified notes trigger reconsideration |
| FR4.5 | SKIP decisions do not persist | Skipped pairs may reappear |
| FR4.6 | Inform user of indexing status | "X notes need indexing" displayed |
| FR4.7 | Allow user to trigger indexing from the UI | "Index Now" button available |

**FR5: Vault Configuration**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR5.1 | Application codebase is separate from vault | No app files in vault |
| FR5.2 | UI must allow user to select/configure vault path | Settings page with path input |
| FR5.3 | On first run, prompt user to select vault path | Prompt displayed if no config |
| FR5.4 | Persist vault path selection for subsequent runs | Path saved to config file |
| FR5.5 | Allow changing vault path from UI | Settings page accessible |
| FR5.6 | State stored inside selected vault (`.obsidian-linker/`) | State travels with vault |
| FR5.7 | Each vault has its own independent state | Switching vaults loads different state |

**FR6: Link Integrity**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR6.1 | Detect incomplete bidirectional links in `## Related` sections | Pairs where only one note links to the other are identified |
| FR6.2 | Surface incomplete links to user for resolution | UI displays list of incomplete links |
| FR6.3 | User must resolve each incomplete link by either completing (add missing link) or removing (delete existing one-way link) | No "ignore" option; all incomplete links must be resolved |
| FR6.4 | Resolution actions follow all FR3 safety requirements | Diff preview shown; per-note confirmation required; atomic writes; audit logged |

**FR7: Document Search**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| FR7.1 | Provide a dedicated search page, accessible from the main navigation | Search page reachable from any screen |
| FR7.2 | Accept a free-text query string from the user | Text input field with submit action |
| FR7.3 | Return a ranked list of notes matching the query, ordered by relevance | Results displayed in descending relevance order |
| FR7.4 | Support three search modes: **FTS** (BM25 lexical), **Semantic** (embedding cosine similarity), and **Hybrid** (RRF combination of both) | All three modes selectable and functional |
| FR7.5 | Allow the user to select the search mode via a UI control (e.g. radio buttons or dropdown) | Mode selection visible on search page; default is Hybrid |
| FR7.6 | Display each result with note title, relevance score, and a content snippet/preview | All three elements visible per result |
| FR7.7 | Allow the user to click a result to view the full rendered note | Clicking a result navigates to or expands the full note content |
| FR7.8 | Search operates over the existing indexed data (embeddings and BM25 index) | No separate indexing step required; search uses the same index as link discovery |
| FR7.9 | Inform the user if notes have not yet been indexed | Warning displayed when index is empty or stale |

---

### 2c) Non-Functional Requirements

**NFR1: Data Integrity and Safety (Highest Priority)**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| NFR1.1 | Prevent accidental modification, corruption, or silent changes to notes | No unintended writes occur |
| NFR1.2 | All write operations must be explicit, auditable, and verifiable | Audit log records every write |
| NFR1.3 | Git serves as the backup mechanism (no separate backup system) | User relies on Git; app does not implement backup |
| NFR1.4 | Vault state stored in `.obsidian-linker/` inside vault | State gitignore-able, travels with vault |
| NFR1.5 | App config stored in `~/.config/obsidian-linker/` | Persists across app updates |

**NFR2: Performance**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| NFR2.1 | Indexing ~200 notes should complete in under 1 minute | Timed benchmark passes |
| NFR2.2 | Candidate generation should be near-instantaneous | < 1 second response time |
| NFR2.3 | Web UI should feel responsive | HTMX partial updates; no full-page reloads |
| NFR2.4 | Document search should return results near-instantaneously | < 1 second response time for all search modes |

**NFR3: Usability**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| NFR3.1 | Single entry point (`obsidian-linker` command launches web app) | Command opens browser to UI |
| NFR3.2 | All actions controllable from the web UI | No separate CLI commands required |
| NFR3.3 | Markdown rendered for readability in review interface | Notes displayed as rendered HTML |
| NFR3.4 | Keyboard shortcuts for efficient review (optional enhancement) | Shortcuts documented if implemented |
| NFR3.5 | Dark mode theme only | No light mode or theme switching |
| NFR3.6 | Display progress bar during indexing operations | Visual feedback during indexing |

**NFR4: Observability**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| NFR4.1 | Use native Python `logging` module with YAML configuration | `logging.yaml` configures logging |
| NFR4.2 | Log messages must follow the 5 Ws: Who, What, When, Where, Why | Log format includes context |
| NFR4.3 | Log file stored in `.obsidian-linker/logs/` inside vault | Logs travel with vault |
| NFR4.4 | Support configurable log levels (DEBUG, INFO, WARNING, ERROR) | Log level changeable via config |

**NFR5: Extensibility**

| ID | Requirement | Fit Criterion |
|----|-------------|---------------|
| NFR5.1 | Embedding provider must use a shared abstract interface (Protocol/ABC) | Interface defined in code |
| NFR5.2 | Easy to swap embedding implementations | New provider requires only implementing interface |
| NFR5.3 | Embedding provider selection configurable without code changes | Config file or UI setting |

---

## 3) Project Issues

### 3.1 Open Issues

*No open issues remaining.*

### 3.2 Off-the-Shelf Solutions

| Option | Considered? | Outcome |
|--------|-------------|---------|
| Obsidian plugins (e.g., Smart Connections) | Yes | Rejected — prefer external tool with more control |
| Manual linking | Yes | Proven insufficient for this user's workflow |

### 3.3 Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Corrupted note during write | Low | High | Atomic writes (temp + rename) |
| Link inserted in wrong location | Low | Medium | Only append to `## Related` section |
| Duplicate links created | Low | Low | Check before insert |
| Lost review decisions | Low | Medium | SQLite with WAL mode |
| App crash mid-apply | Low | Medium | Process one note at a time; audit log enables recovery |
| Note renamed between runs | Medium | Low | Track by content hash, not just path |

### 3.4 Waiting Room (Deferred Ideas)

| Idea | Rationale for Deferral |
|------|------------------------|
| Multi-vault support | Complexity not justified for current use case |
| Tag suggestions | Different feature |
| Suggest merging duplicate notes | Different problem |
| Real-time watch mode | On-demand is sufficient |

### 3.5 Success Criteria

| ID | Criterion |
|----|-----------|
| SC-1 | User can identify related notes they would have missed manually |
| SC-2 | Review process is efficient (< 30 seconds per pair decision) |
| SC-3 | Zero unintended modifications to notes |
| SC-4 | State persists correctly across sessions |
| SC-5 | Changed notes are detected and re-indexed automatically |

---

## 4) Naming Conventions and Definitions

### Glossary

| Term | Definition |
|------|------------|
| **Vault** | An Obsidian vault — a folder containing markdown notes and `.obsidian/` config |
| **Note** | A single markdown file (`.md`) in the vault |
| **Candidate pair** | Two notes identified as potentially related by the similarity algorithm |
| **Decision** | User's verdict on a candidate pair: YES, NO, or SKIP |
| **RRF** | Reciprocal Rank Fusion — algorithm for combining rankings from multiple sources |
| **BM25** | Best Match 25 — a lexical ranking function for text search |
| **FTS** | Full-Text Search — lexical keyword-based search (implemented via BM25 in this application) |
| **Embedding** | A vector representation of text for semantic similarity comparison |
| **Body link** | A one-directional link within the main content of a note (contextual, manual) |
| **Related link** | A bidirectional link in the `## Related` section (managed by this application) |
| **Bidirectional link** | For `## Related` section: both notes must link to each other. Body links can be one-directional. |

### Data Dictionary

| Data Item | Type | Description |
|-----------|------|-------------|
| `note_path` | `Path` | Relative path to note within vault |
| `content_hash` | `str` | SHA256 hash of note content |
| `embedding` | `list[float]` | Vector representation of note content |
| `rrf_score` | `float` | Combined similarity score (higher = more similar) |
| `decision` | `Enum` | YES, NO, or SKIP |
| `decision_hash` | `str` | Content hash of note at time of decision (for invalidation) |

---

## State Management

| State Type | Location | Purpose |
|------------|----------|---------|
| **App config** | `~/.config/obsidian-linker/config.json` | Stores vault path selection; persists across app updates |
| **Vault state** | `<vault>/.obsidian-linker/` | Embeddings, decisions, logs; travels with vault |
| **App codebase** | Wherever you clone/install it | No state stored here |

| State | Storage | Location |
|-------|---------|----------|
| Note metadata | SQLite | `<vault>/.obsidian-linker/state.db` |
| Embeddings | SQLite | `<vault>/.obsidian-linker/state.db` |
| Lexical index | In-memory | Rebuilt on startup |
| Review decisions | SQLite | `<vault>/.obsidian-linker/state.db` |
| Audit log | SQLite | `<vault>/.obsidian-linker/state.db` |
| Application logs | File | `<vault>/.obsidian-linker/logs/` |

**Change detection:** SHA256 content hash (not mtime)

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

### Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | User requirement |
| Dependency management | `uv` | User requirement |
| Web framework | FastAPI | Modern, async, good DX |
| Templating | Jinja2 | Standard, well-integrated |
| Frontend interactivity | HTMX | Partial updates, no build step |
| CSS | Pico.css (CDN), dark mode only | Classless, minimal effort, matches Obsidian aesthetic |
| Markdown rendering | mistune | Fast, minimal deps |
| ORM | SQLModel | Pydantic integration, FastAPI author |
| Embeddings | model2vec (default, swappable) | Local, fast static embeddings |
| Lexical search | bm25s | Actively maintained BM25 implementation |
| Score fusion | Reciprocal Rank Fusion | Robust to scale differences |
| Database | SQLite | Single file, simple |
| Logging | Python `logging` + PyYAML | Native, configurable via YAML, 5 Ws format |

### Similarity Algorithm

1. **Semantic similarity:** Embed all notes with configured embedding provider, compute cosine similarity
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
6. **Search:** Navigate to search page → enter query → select mode (FTS/semantic/hybrid) → browse matching notes

### Changing Vault
- Access settings from dashboard to select a different vault path
- Each vault maintains its own independent state

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 4 | — | Original requirements document |
| 5 | — | Refined: Python 3.12+; decision invalidation on note modification; per-pair explainability; exclude already-linked pairs; FR6 Link Integrity; glossary additions |
| 6 | — | Added FR7 Document Search: dedicated search page with FTS, semantic, and hybrid search modes; glossary addition (FTS) |
