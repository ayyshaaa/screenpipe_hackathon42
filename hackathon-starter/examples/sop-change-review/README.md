<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# SOP change review

Show a process owner what changed between two procedure documents before reviewing a new version.

## Run the fictional demo

From the repository root, with Bun 1.3 or newer:

```sh
bun run changes
```

Revision 2 proposes a second operator checking totals. The source quote does not establish that policy, so the fixture includes an unanswered question. The report shows the proposed instruction and context changes.

The report prints to the terminal and is saved to a new Markdown file under ignored `output/`. See [sample output](sample-output.md). No API key, account, model call or network integration is needed.

## Use your own input

```sh
bun run changes --before local-data/before.json --after local-data/after.json
```

Two procedure documents produced by the SOP starter, or approved JSON snapshots exported by the review desk. Both are validated. Approved snapshots also have their fingerprints checked. Steps are compared by position, so reordering is visible. This does not align semantically equivalent steps or certify a change.

Start from [the fixture](../../sample-data/procedure-draft.json) or [capture a permissioned session](../../docs/local-data.md). For captured records, first run `bun run sop --input local-data/records.json` and review that procedure; raw capture arrays are not procedure documents. Inputs are read locally and remain unchanged. The CLI refuses unknown options and JSON files over 2 MB. Reports contain source text, so inspect them before sharing. A generated draft does not send a message, assign a ticket or update a customer record.

## Acceptance test

Changing step order, classification, quote or review state must appear. A modified approved snapshot must be rejected. Unchanged documents must report no content or step changes.

Run `bun test` for the automated checks. Then have someone else inspect the report against the fixture and explain what they would do next.

## Build further

Build a side-by-side review UI with evidence previews and accept/reject controls. Group changes by stable step IDs when you add them to the schema. Preserve the earlier approved snapshot.

Implementation: [shared project functions](../../src/projects.ts), [CLI](../../src/project-cli.ts). Fork this repository and change the function for this project; the other starters remain available for comparison. These are hackathon building blocks, not validated production integrations.
