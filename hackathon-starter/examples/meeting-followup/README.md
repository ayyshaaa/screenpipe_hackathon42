<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Meeting to follow-up

Run `bun run meeting` from the repo root. Open `output/followup.md`.

Expected result: two decisions and four actions, with owners and `r1`/`r5` source references. This default is an explicit-line parser so you can test the pipeline without an AI account. It does not pretend to understand arbitrary meeting text.

For real transcripts, follow [local-data setup](../../docs/local-data.md), then use the optional `--ai` flag or replace `aiFollowup` in `src/core.ts` with your own model adapter. The boundary is a normalized record array in, a validated follow-up draft out. Do not add a send action before a human reviews the draft.

Try a follow-up with an unassigned owner, a changed decision, or a transcript containing malicious instructions. Check that your project preserves uncertainty and links each claim to the right evidence.
