# Metricool daily import v1 — read-only

This adapter consumes **owner-authorized Metricool analytics response JSON** and produces a daily report for YouTube, Instagram Reels, TikTok. It is not a direct authenticated API connector, has no credentials and does not perform network requests.

The ChatGPT Metricool connector can retrieve the response; export the JSON as a file and pass it to the importer. A separate approved connector would be needed for unattended recurring synchronization.

## Required query field IDs

Call Metricool `getAnalyticsDataByMetrics` for the same date interval, using brand ID of the owner-connected account, with fields in this exact order:

- YouTube: `YTEV02` (evolution video views), `YTEV01` (subscribers)
- Instagram: `IGEV23` (evolution Reels views), `IGEV01` (followers)
- TikTok: `TKEV02` (evolution video views), `TKEV07` (followers)

The response JSON shape is `{"rows":[["123.0",null,"20261029"]]}`: metrics in requested order and the last column is a YYYYMMDD date. Never interpret null as zero. Unexpected row shapes, duplicate dates and invalid counts are rejected.

## Usage

```python
from tools.autoposter.src.crossplatform.metricool_daily import (
    FIELD_IDS, import_metricool_daily, build_daily_report, load_metricool_response
)

platforms = ["youtube", "instagram", "tiktok"]
imports = [
    import_metricool_daily(
        p,
        load_metricool_response(f"{p}.json"),
        metric_ids=list(FIELD_IDS[p].values()),
        collected_at="2026-10-30T12:00:00+03:00",
    )
    for p in platforms
]
report = build_daily_report(imports)
```

Run tests: `python -m unittest tools.autoposter.tests.test_metricool_daily`.

**Do not feed these daily rows to the existing per-post analytics importer.** Daily evolution aggregates may mix content published at different times. No article matching, post-age normalization, conversion attribution or cross-platform view equivalence is asserted.

The connected Metricool brand was queried manually on 2026-10-30 and returned daily data; the data are not committed to the repository. This adapter does not activate `CROSS_PLATFORM_GROWTH_ENABLED` or edit any publishing integration.
