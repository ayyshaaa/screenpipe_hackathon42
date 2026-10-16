<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Evidence search

Find the original work context behind a phrase before answering a teammate’s question.

## Run the fictional demo

From the repository root, with Bun 1.3 or newer:

```sh
bun run search
```

The phrase export returns four records, including the failed retry and the later partial result. A query with no match produces an explicit empty result.

The report prints to the terminal and is saved to a new Markdown file under ignored `output/`. See [sample output](sample-output.md). No API key, account, model call or network integration is needed.

## Use your own input

```sh
bun run search --input local-data/records.json --query "export"
```

An ordinary captured record array; annotations are not required. Search matches a literal phrase in text, ignoring case. It returns complete matching record text with source ID, timestamp and app.

Start from [the fixture](../../sample-data/team-session.json) or [capture a permissioned session](../../docs/local-data.md). Inputs are read locally and remain unchanged. The CLI refuses unknown options and JSON files over 2 MB. Reports contain source text, so inspect them before sharing. A generated draft does not send a message, assign a ticket or update a customer record.

## Acceptance test

Search for export and get four sourced results. Search for a phrase absent from the fixture and get no invented answer. Search regex characters literally.

Run `bun test` for the automated checks. Then have someone else inspect the report against the fixture and explain what they would do next.

## Build further

Add app/time filters, then an optional answer generator that cites exact excerpts. Keep the original result set visible and require an explicit “insufficient evidence” outcome. Source matching alone does not prove an answer is correct.

Implementation: [shared project functions](../../src/projects.ts), [CLI](../../src/project-cli.ts). Fork this repository and change the function for this project; the other starters remain available for comparison. These are hackathon building blocks, not validated production integrations.
