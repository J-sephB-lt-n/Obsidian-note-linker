"""CLI entry point for the Obsidian Note Linker web application."""

import uvicorn


def main() -> None:
    """Launch the Obsidian Note Linker web application on localhost:8000."""
    uvicorn.run(
        "obsidian_note_linker.api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
