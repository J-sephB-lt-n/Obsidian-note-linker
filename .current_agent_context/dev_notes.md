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
