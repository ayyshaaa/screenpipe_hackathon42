<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Workflow review desk

Run `bun start` and open http://localhost:4242. Edit the proposed instructions, inspect source excerpts, classify each observation, and answer the open questions. Classification changes and instruction edits reset that observation's review checkbox. Changes to the title or overall context reset all observation reviews.

Approval requires a nonempty title and context, at least one normal process step, every record accounted for, all observations classified and reviewed, answered questions and a reviewer name. You can export an incomplete draft to continue later.

**Approve and freeze** creates a deep-copied snapshot with the source evidence, revision, reviewer, timestamp and SHA-256 fingerprint. Export it, and use **Export SOP (.md)** for a readable handoff with the same evidence and review fingerprint. The desk disables edits until **Start a new revision** makes a separate draft, references the parent fingerprint and resets review checks. Importing a changed approved JSON fails integrity verification.

This is local review, with self-attested names. Anyone who controls a file can construct another hash, so it is not authenticated sign-off. Data stays in the tab until exported; reloads lose unsaved edits. Exports include source excerpts. The fixture has text evidence; live captures include original-context links where available, not embedded screenshots.

Useful extensions: permissioned screenshot attachments with content hashes, attributed comments, authenticated approvers and revision comparisons. If you add collaboration, define who may see source material and who may approve a version before adding sharing.
