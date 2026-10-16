<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Support escalation packet

Give an engineer a sourced incident timeline: symptoms, attempted fixes, observed results and questions still needing an answer.

## Run the fictional demo

From the repository root, with Bun 1.3 or newer:

```sh
bun run escalation
```

The fictional export times out. Reloading fails; a smaller export works, but full-month recovery remains unverified. Maya has a next action and another action is explicitly unassigned.

The report prints to the terminal and is saved to a new Markdown file under ignored `output/`. See [sample output](sample-output.md). No API key, account, model call or network integration is needed.

## Use your own input

```sh
bun run escalation --input local-data/records.json
```

Symptom:, Attempt:, Result:, Question: and Action (Owner): lines. Add or review these annotations yourself; the starter does not infer them from arbitrary capture text.

Start from [the fixture](../../sample-data/team-session.json) or [capture a permissioned session](../../docs/local-data.md). Inputs are read locally and remain unchanged. The CLI refuses unknown options and JSON files over 2 MB. Reports contain source text, so inspect them before sharing. A generated draft does not send a message, assign a ticket or update a customer record.

## Acceptance test

Keep both the failed reload and the partial success in the timeline. Leave full recovery unverified. Sort out-of-order records by timestamp and retain each source ID.

Run `bun test` for the automated checks. Then have someone else inspect the report against the fixture and explain what they would do next.

## Build further

Add a local review form that lets the operator choose evidence, mark obsolete attempts and export a ticket draft. Require an operator to confirm current impact before an integration creates a ticket.

Implementation: [shared project functions](../../src/projects.ts), [CLI](../../src/project-cli.ts). Fork this repository and change the function for this project; the other starters remain available for comparison. These are hackathon building blocks, not validated production integrations.
