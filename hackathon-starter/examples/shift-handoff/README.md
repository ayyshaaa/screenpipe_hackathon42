<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Shift handoff

Help the next operator see the explicit decisions, unresolved blockers and named next actions from a work session.

## Run the fictional demo

From the repository root, with Bun 1.3 or newer:

```sh
bun run handoff
```

The last verified report stays available. The new export is still blocked. Maya owns a test; an investigation action remains unassigned.

The report prints to the terminal and is saved to a new Markdown file under ignored `output/`. See [sample output](sample-output.md). No API key, account, model call or network integration is needed.

## Use your own input

```sh
bun run handoff --input local-data/records.json
```

Decision:, Blocker: and Action (Owner): lines. Use Unassigned explicitly when an owner is unknown. Free text stays outside the structured handoff.

Start from [the fixture](../../sample-data/team-session.json) or [capture a permissioned session](../../docs/local-data.md). Inputs are read locally and remain unchanged. The CLI refuses unknown options and JSON files over 2 MB. Reports contain source text, so inspect them before sharing. A generated draft does not send a message, assign a ticket or update a customer record.

## Acceptance test

The blocker remains visible after a partial recovery. Owner names must come from annotations. A line such as “maybe ask Sam” must not silently assign Sam a task.

Run `bun test` for the automated checks. Then have someone else inspect the report against the fixture and explain what they would do next.

## Build further

Add receiver acknowledgement and a status history. Link each changed status to evidence and keep the original handoff available. A Slack or ticket integration can be added after a person reviews the draft.

Implementation: [shared project functions](../../src/projects.ts), [CLI](../../src/project-cli.ts). Fork this repository and change the function for this project; the other starters remain available for comparison. These are hackathon building blocks, not validated production integrations.
