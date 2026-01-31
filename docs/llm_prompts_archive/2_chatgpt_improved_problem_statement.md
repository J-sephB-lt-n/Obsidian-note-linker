You are designing a Python application to help me identify and manage links between Obsidian notes.

## Background / Problem

- I write ~1 Obsidian note per day.
- Many notes are semantically or thematically related, but I often fail to link them, especially when they are written far apart in time.
- As a result:
  - My Obsidian graph is less useful than it should be.
  - Related notes fall off my radar.
  - In some cases, I accidentally duplicate work by writing very similar notes multiple times.

Manual linking has proven insufficient.

## Primary Goal

Build a Python application that helps me _safely_ discover, review, and (optionally) create links between related Obsidian notes.

## Core Requirements

### 1. Link Discovery

- Analyze a corpus of Obsidian markdown notes.
- Identify pairs of notes that are semantically/thematically related.
- Assign a similarity score or confidence level to each proposed pair.
- The similarity method should be explainable at a high level (e.g., embeddings, topic similarity).

### 2. Human-in-the-Loop Review

- Provide an efficient interface (CLI or GUI is acceptable) that:
  - Displays two candidate notes side by side (or otherwise clearly).
  - Shows why they were suggested as related (e.g., similarity score, shared themes).
  - Allows me to explicitly record a **Yes / No / Skip** decision for each pair.

### 3. Safe Link Creation (Optional, Strongly Constrained)

- I am extremely risk-averse about automatic modification of my notes.
- By default, the application **must not** edit any note files.
- If automatic writing is implemented, it must:
  - Be clearly optional and disabled by default.
  - Require explicit user confirmation per link.
  - Be fully transparent and verifiable (e.g., dry-run mode, diff preview).
  - Never overwrite existing content unexpectedly.
- It is acceptable (and possibly preferable) for this application to only _suggest_ links and record decisions externally.

### 4. Incremental / Repeated Use

- I will run this application repeatedly over time.
- Most notes will be unchanged between runs, with a small number of new notes added.
- The design should account for this (e.g., caching embeddings, avoiding re-processing unchanged notes, not showing me the same suggested pairs every time).

### 5. Data Integrity and Safety (Highest Priority)

- Prevent accidental modification, corruption, or silent changes to notes.
- Any operation that could alter notes must be:
  - Explicit
  - Auditable
  - Easy to verify before execution

## Definition of a “Linked” Note

- Each note contains a section titled `## Related`.
- Links are standard Obsidian markdown links.
- _Both_ articles in a linked pair contain a link to the other.

Example:

```markdown
## Related

- [No Vibes Allowed - Solving Hard Problems in Complex Codebases Dex Horthy HumanLayer (presentation at AI Engineer 2025)](<No%20Vibes%20Allowed%20-%20Solving%20Hard%20Problems%20in%20Complex%20Codebases%20Dex%20Horthy%20HumanLayer%20(presentation%20at%20AI%20Engineer%202025).md>)
- [Effective harnesses for long-running agents (Anthropic Engineering Blog)](<Effective%20harnesses%20for%20long-running%20agents%20(Anthropic%20Engineering%20Blog).md>)
```
