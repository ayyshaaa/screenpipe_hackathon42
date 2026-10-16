<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Onboarding walkthrough

Give a new operator a practice sheet derived from a procedure, with room to record results and ask for clarification.

## Run the fictional demo

From the repository root, with Bun 1.3 or newer:

```sh
bun run onboarding
```

Four normal reporting steps become unchecked practice items. Refunded orders and the one-off browser refresh go in a separate discussion section. The unanswered eligibility question stays unanswered.

The report prints to the terminal and is saved to a new Markdown file under ignored `output/`. See [sample output](sample-output.md). No API key, account, model call or network integration is needed.

## Use your own input

```sh
bun run onboarding --input local-data/approved.json
```

A validated procedure draft or an approved JSON snapshot. Drafts are clearly labeled. Approved snapshots are verified before use. Review the instructions with the process owner before training someone.

Start from [the fixture](../../sample-data/procedure-draft.json) or [capture a permissioned session](../../docs/local-data.md). For captured records, first run `bun run sop --input local-data/records.json` and review that procedure; raw capture arrays are not procedure documents. Inputs are read locally and remain unchanged. The CLI refuses unknown options and JSON files over 2 MB. Reports contain source text, so inspect them before sharing. A generated draft does not send a message, assign a ticket or update a customer record.

## Acceptance test

Every practice checkbox starts empty. Troubleshooting must not appear as a normal step. Unanswered questions stay visible; exporting a worksheet never marks the learner competent.

Run `bun test` for the automated checks. Then have someone else inspect the report against the fixture and explain what they would do next.

## Build further

Add a learner view that records where help was needed. Test with a teammate who has not seen the task, then feed their clarification requests into a new SOP revision.

Implementation: [shared project functions](../../src/projects.ts), [CLI](../../src/project-cli.ts). Fork this repository and change the function for this project; the other starters remain available for comparison. These are hackathon building blocks, not validated production integrations.
