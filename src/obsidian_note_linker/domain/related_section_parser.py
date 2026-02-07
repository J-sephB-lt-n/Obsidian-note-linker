"""Parser for ``## Related`` sections in Obsidian markdown notes.

Extracts links from the ``## Related`` section to detect which note
pairs are already linked, enabling the candidate generation pipeline
to exclude them (FR1.6).
"""

import re
from pathlib import Path
from urllib.parse import unquote

# Matches the Obsidian link format used in ## Related sections:
#   - [Note Title](<Note%20Title.md>)
_LINK_PATTERN = re.compile(r"- \[.*?\]\(<(.+?)>\)")


def parse_related_links(content: str) -> list[Path]:
    """Extract linked note paths from a note's ``## Related`` section.

    Only links inside the ``## Related`` section are considered.  The
    section ends at the next ``##``-level heading or end of file.
    Percent-encoded paths (e.g. ``Note%20Title.md``) are decoded.

    Args:
        content: Raw markdown content of the note.

    Returns:
        List of relative paths to linked notes.
    """
    # Find the ## Related section
    related_match = re.search(r"^## Related\s*$", content, flags=re.MULTILINE)
    if not related_match:
        return []

    # Extract text from ## Related to next heading or EOF
    section_start = related_match.end()
    next_heading = re.search(r"^## ", content[section_start:], flags=re.MULTILINE)
    if next_heading:
        section_text = content[section_start : section_start + next_heading.start()]
    else:
        section_text = content[section_start:]

    # Extract all links from the section
    return [
        Path(unquote(match.group(1)))
        for match in _LINK_PATTERN.finditer(section_text)
    ]


def get_existing_link_pairs(
    notes: dict[Path, str],
) -> set[tuple[Path, Path]]:
    """Identify bidirectionally linked note pairs from ``## Related`` sections.

    A pair (A, B) is included only when A's ``## Related`` links to B
    **and** B's ``## Related`` links to A.

    Args:
        notes: Mapping of note relative path → raw markdown content.

    Returns:
        Set of canonically sorted ``(path_a, path_b)`` tuples where
        ``path_a < path_b``.
    """
    # Build one-directional link map: source → set of targets
    link_map: dict[Path, set[Path]] = {}
    for note_path, content in notes.items():
        linked = parse_related_links(content)
        if linked:
            link_map[note_path] = set(linked)

    # Find bidirectional pairs
    pairs: set[tuple[Path, Path]] = set()
    for source, targets in link_map.items():
        for target in targets:
            if target in link_map and source in link_map[target]:
                pair = tuple(sorted([source, target]))
                pairs.add(pair)  # type: ignore[arg-type]

    return pairs
