"""Link builder — format Obsidian links and modify note content.

Provides pure functions for building the ``## Related`` section:
formatting individual links, inserting links into existing note content
(creating or appending the section), and computing diffs for preview.
"""

import difflib
import re
from pathlib import Path
from urllib.parse import quote

from obsidian_note_linker.domain.related_section_parser import parse_related_links


def format_obsidian_link(note_path: Path) -> str:
    """Format a note path as an Obsidian markdown list-item link.

    Uses the format ``- [Note Title](<Note%20Title.md>)`` where the
    title is the filename stem and the path is percent-encoded.

    Args:
        note_path: Relative path to the target note (e.g. ``My Note.md``).

    Returns:
        Formatted link string.
    """
    title = note_path.stem
    encoded_path = quote(str(note_path))
    return f"- [{title}](<{encoded_path}>)"


def insert_links_into_content(content: str, links: list[str]) -> str:
    """Insert links into a note's ``## Related`` section.

    Creates the section if it doesn't exist, or appends to it if it
    does.  Duplicate links (already present in the section) are
    silently skipped (FR3.9).

    Args:
        content: Raw markdown content of the note.
        links: List of formatted link strings to insert.

    Returns:
        Modified content with the new links inserted.
    """
    if not links:
        return content

    # Determine which links are actually new (duplicate prevention)
    existing_link_paths = {str(p) for p in parse_related_links(content)}
    new_links = [
        link for link in links
        if _extract_path_from_link(link) not in existing_link_paths
    ]

    if not new_links:
        return content

    new_links_block = "\n".join(new_links) + "\n"

    # Check if ## Related section already exists
    related_match = re.search(r"^## Related\s*$", content, flags=re.MULTILINE)

    if related_match:
        return _append_to_existing_section(content, related_match, new_links_block)
    else:
        return _create_new_section(content, new_links_block)


def compute_content_diff(original: str, modified: str, filename: str) -> str:
    """Compute a unified diff between original and modified content.

    Args:
        original: Original file content.
        modified: Modified file content.
        filename: Name shown in the diff header.

    Returns:
        Unified diff string, or empty string if no changes.
    """
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    ))

    if not diff_lines:
        return ""

    return "\n".join(line.rstrip("\n") for line in diff_lines)


def _extract_path_from_link(link: str) -> str:
    """Extract the decoded note path from a formatted link string.

    Args:
        link: Formatted link like ``- [Title](<path>)``.

    Returns:
        The decoded path string, or the original link if parsing fails.
    """
    match = re.search(r"<(.+?)>", link)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    return link


def _append_to_existing_section(
    content: str,
    related_match: re.Match[str],
    new_links_block: str,
) -> str:
    """Append links to an existing ``## Related`` section.

    Inserts new links after existing links but before the next heading.

    Args:
        content: Full note content.
        related_match: Regex match for the ``## Related`` heading.
        new_links_block: Newline-joined block of link strings to insert.

    Returns:
        Modified content.
    """
    section_start = related_match.end()

    # Find the end of the Related section (next ## heading or EOF)
    next_heading = re.search(r"^## ", content[section_start:], flags=re.MULTILINE)

    if next_heading:
        insert_pos = section_start + next_heading.start()
        # Ensure there's a newline before the new links
        before = content[:insert_pos].rstrip("\n") + "\n"
        after = "\n" + content[insert_pos:]
        return before + new_links_block + after
    else:
        # Section goes to EOF — append at the end
        trimmed = content.rstrip("\n") + "\n"
        return trimmed + new_links_block


def _create_new_section(content: str, new_links_block: str) -> str:
    """Create a new ``## Related`` section at the end of the note.

    Args:
        content: Full note content.
        new_links_block: Newline-joined block of link strings to insert.

    Returns:
        Modified content with new section appended.
    """
    trimmed = content.rstrip("\n")
    return trimmed + "\n\n## Related\n\n" + new_links_block
