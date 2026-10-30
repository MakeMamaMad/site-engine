# Linking publication URLs to source articles

Short Generator v2 already saves `content_key`, `slug`, and `title` to `out_v2/manifest.json`. This provides a canonical identifier for rendered content but does **not** prove what URL each social platform published.

After an authorized publisher successfully posts, store a *receipt* with exactly:
```json
{"content_key": "actual_manifest_content_key", "platform": "youtube", "post_url": "https://www.youtube.com/watch?v=SvIrsKeSnw0"}
```
Use real values for each platform. Verify receipts against archived manifests and publishing logs. Do not synthesize URLs from publishing times.

`receipt_mapping(manifests, receipts)` produces a validated mapping of canonical post URL to content key. The Metricool per-post adapter's `apply_owner_mapping` can use this mapping. Both functions are offline/read-only.

**Important:** The current generator uses a single `out_v2/manifest.json` output path, overwritten by subsequent runs. Production must preserve historical manifests alongside receipts (or an equivalent durable source log) before enabling unattended linkage. Without that history, old publications remain unmapped until explicitly approved.

No publisher is modified. No credentials or private analytics are stored in Git. No schedules, production flags or weights are changed. Run `python -m unittest tools.autoposter.tests.test_publication_receipts`.
