I am writing a LOT of obsidian notes (average of 1 per day), but I am not connecting notes which are directly related, so my obsidian graph is not that useful.
I am making effort to link notes together by hand but notes that are separated in time (even if directly related) fall off the radar. In extreme cases, I am even duplicating work by writing the same (or very similar) note twice.

I want a python application which I can use to:

- Discover potential links between notes which are semantically/thematically related (and measure the strength of their similarity).
- An efficient interface for viewing 2 notes that might be potentially linked, and to record and/or action my yes/no decision.
- If it's feasible and safe, if I say yes to a proposed pair of notes, then links of the correct format should be added into both notes. I'm very scared to mess up existing notes and links, so I might keep this "auto-write" functionality out of this application. If this functionality is added, then it needs to be VERY verifiable and explicit and safe.
- I will use this application repeatedly (and most of the notes will be the same on every run, with the addition of a few new ones), so this needs to be taken into account.

Again, a primary consideration for me is that my notes are not accidentally edited/damaged in some way by this application (especially without me noticing).

## Note Linking

All of my notes have a "Related" section in them linking to other notes like this:

```markdown
## Related

- [No Vibes Allowed - Solving Hard Problems in Complex Codebases Dex Horthy HumanLayer (presentation at AI Engineer 2025)](<No%20Vibes%20Allowed%20-%20Solving%20Hard%20Problems%20in%20Complex%20Codebases%20Dex%20Horthy%20HumanLayer%20(presentation%20at%20AI%20Engineer%202025).md>)
- [Effective harnesses for long-running agents (Anthropic Engineering Blog)](<Effective%20harnesses%20for%20long-running%20agents%20(Anthropic%20Engineering%20Blog).md>)
```

I consider 2 notes to be linked if BOTH contain links to each other.
