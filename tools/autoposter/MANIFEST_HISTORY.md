# Short v2 render manifest history

The generator writes `out_v2/manifest.json`, which is replaced each run. A new append-only snapshot is also stored under `out_v2/manifest_history/<sha256>.json` after each successful render. Snapshots are keyed by the complete manifest content and do not overwrite distinct renders. The normal `manifest.json` output remains unchanged.

**Important**: This is local filesystem history, not guaranteed persistent storage. Ephemeral CI runners delete files between jobs. To retain history, a deployment operator must explicitly persist or export `out_v2/manifest_history` as a durable artifact or volume. Do not commit media or private metrics to the repository. No scheduled job or credentials are added here.

Render manifest != successful publication. The separate `publication_receipts.py` mapping requires verified posted URLs and matching `content_key` before post-to-article attribution. Never guess from timestamp/title. No social account is modified and no additional API calls are made.

Run: `python -m unittest tools.autoposter.tests.test_manifest_history`.
