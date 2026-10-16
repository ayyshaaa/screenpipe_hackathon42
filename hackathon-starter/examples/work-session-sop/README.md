<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Work session to a reviewable SOP

Capture one permissioned work session using [local-data setup](../../docs/local-data.md). The input is a normalized array of Screenpipe records with IDs, timestamps, application names and text.

`bun run sop --input local-data/records.json` preserves observations as unclassified draft entries. It does not assume that every observed action belongs in the normal process.

`bun run sop --input local-data/records.json --ai` explicitly sends those records to your configured provider. It asks for instructions, context, normal/exception/troubleshooting classifications, exact evidence quotes and unresolved questions. Returned quotes must match their referenced records. Model-supplied approvals and executable bindings are discarded. The adapter is covered by mocked provider tests; real-provider quality must be evaluated on your own task.

Open the result with `bun start --draft output/procedure-draft.json`. A draft is useful only when the process owner can check it against what happened. Account for every input record, including irrelevant troubleshooting, before approval.

The sample demonstrates why classification matters: a one-off export page refresh should not become a mandatory daily step, while excluding a refunded order is a real exception rule.

Try extending the project to compare two sessions of the same task. Show which steps repeat, which vary and where there is insufficient evidence. Measure corrections and missing context before claiming time saved. Keep private customer records out of the public repo.
