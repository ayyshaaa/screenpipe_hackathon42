<!-- screenpipe — AI that knows everything you've seen, said, or heard -->
<!-- https://screenpipe.com -->
# Connect local Screenpipe data

1. Open Screenpipe and record a short test session. Use non-sensitive content.
2. Copy `.env.example` to `.env` with your editor. Get the local API key privately with `screenpipe auth token` and put it in `SCREENPIPE_LOCAL_API_KEY`. Never paste the key into an issue, chat, video or commit. If using an AI assistant instead of these scripts, Settings > Connections configures the Screenpipe MCP integration.
3. Run `bun run doctor`. An empty result means authentication worked but there may be no recent captured data. A 401/403 means the key needs checking; connection refused means the app/API is unavailable at the configured local address.
4. Capture a bounded window, replacing these example timestamps with your own:

```sh
bun run capture --start 2026-10-16T16:00:00Z --end 2026-10-16T17:00:00Z
```

For a meeting transcript, add `--type audio`. This saves at most 20 records to ignored `local-data/records.json`; it is not a complete export. Open that file and inspect it before continuing.

```sh
bun run sop --input local-data/records.json
bun start --draft output/procedure-draft.json
```

The dashboard stays on loopback. Original-evidence links open Screenpipe. No outside server receives these records through the starter unless you explicitly use `--ai`.

## Optional AI extraction

Set `AI_BASE_URL`, `AI_MODEL` and `AI_API_KEY` in `.env`. The adapter uses the OpenAI-compatible chat-completions JSON format. Your chosen provider must support `response_format: {type: "json_object"}`. Compatibility with every provider is not guaranteed.

```sh
bun run sop --input local-data/records.json --ai
```

This sends the selected records to the configured provider and writes an unapproved SOP candidate. Unknown evidence IDs and quotes that do not occur in their source are rejected. A matching quote does not prove an instruction is correct; review each claim, exception and missing-context question. Provider compatibility and output quality need checking on your selected model. The output has no send action.

## Troubleshooting

- `bun` not found: install Bun from its official site and reopen your terminal.
- Port 4242 occupied: stop your own previous starter or set a different `PORT` environment variable. Do not stop someone else's process.
- Optional meeting example, no actions extracted: sample mode only recognizes `Decision:` and `Action (Owner):` lines. Use the optional AI adapter for ordinary transcripts, or add reviewed annotations yourself.
- Screenpipe key unavailable: sample mode still works. Ask for technical help in the event Discord without posting credentials or raw private recordings.
- macOS and Windows: scripts use Bun and platform-neutral paths. CI runs the sample/test commands on both systems and Linux. A CI pass is not proof of live Screenpipe capture on every machine.

Without `--ai`, SOP generation preserves unclassified observations for manual review. It does not infer a standard process. Export drafts before closing the review tab; local edits are not autosaved.
