<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Repeated-task finder

Choose an automation experiment using repeated, manually annotated task runs and their observed durations.

## Run the fictional demo

From the repository root, with Bun 1.3 or newer:

```sh
bun run repetition
```

Weekly reporting has two distinct runs totaling 27 minutes. A duplicate capture of week-b does not add another run. Account setup has two runs totaling 17 minutes; a one-time incident is excluded.

The report prints to the terminal and is saved to a new Markdown file under ignored `output/`. See [sample output](sample-output.md). No API key, account, model call or network integration is needed.

## Use your own input

```sh
bun run repetition --input local-data/records.json
```

Each annotated record has exactly one Task:, Run: and Minutes: line. Task labels group exactly; Run identifies one occurrence within that task. Minutes must be greater than zero and at most 1,440. Duplicate captures of a run may agree; conflicting durations stop the report. Unannotated records are ignored.

Start from [the fixture](../../sample-data/task-runs.json) or [capture a permissioned session](../../docs/local-data.md). Inputs are read locally and remain unchanged. The CLI refuses unknown options and JSON files over 2 MB. Reports contain source text, so inspect them before sharing. A generated draft does not send a message, assign a ticket or update a customer record.

## Acceptance test

Do not count duplicate captures twice. Reject contradictory durations and incomplete annotations. Exclude tasks with one run. Show the source IDs behind each candidate, without predicting savings.

Run `bun test` for the automated checks. Then have someone else inspect the report against the fixture and explain what they would do next.

## Build further

Build a diary UI for reviewing task boundaries and timing runs. Compare repeated sessions, then measure the same task manually and with assistance. Add evidence-based acceptance criteria before ranking by estimated benefit.

Implementation: [shared project functions](../../src/projects.ts), [CLI](../../src/project-cli.ts). Fork this repository and change the function for this project; the other starters remain available for comparison. These are hackathon building blocks, not validated production integrations.
