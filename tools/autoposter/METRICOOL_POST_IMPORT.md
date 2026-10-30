# Metricool per-post import (read-only)

This is a per-publication companion to the existing Metricool **daily** importer. The two formats must never be conflated.

## Provider queries

Use owner-connected Metricool analytics \`getAnalyticsDataByMetrics\` with **these exact field IDs in order**:

- YouTube: \`YTVP02,YTVP05,YTVP06,YTVP17\` (date/time, URL, views, title)
- Instagram Reels: \`IGRE02,IGRE06,IGRE23\` (date/time, URL, views)
- TikTok videos: \`TKPO02,TKPO03,TKPO07\` (date/time, URL, views)

For October 2026, the verified connected brand returned entries for all three platforms, but some YouTube views were null. Null means **unknown**, not zero.

## Example

\`\`\`python
from tools.autoposter.src.crossplatform.metricool_posts import SCHEMAS, import_posts, apply_owner_mapping
batch = import_posts("instagram",
    {"rows": [["20261029162902", "https://www.instagram.com/reel/DfFb7_7DPDk/", "86"]]},
    metric_ids=list(SCHEMAS["instagram"]), collected_at="2026-10-30T10:00:00+03:00")
report = apply_owner_mapping([batch], {
    "https://www.instagram.com/reel/DfFb7_7DPDk": "OWNER_APPROVED_ARTICLE_ID"
})
\`\`\`

The date/time values are interpreted using the account timezone (default \`Europe/Minsk\`) unless a different verified account timezone is passed. Verify provider timezone semantics before post-age comparisons.

Only explicit owner-verified mappings of post URLs to a canonical article/content ID permit matching. Similar titles and close publish times may be suggested for **manual review**, never automatically declared matched.

Metricool returns current observations, not necessarily 24-hour / 7-day historical snapshots. The existing cross-platform analytics window comparator requires actual timestamp-aligned observations: don't fabricate them from current totals.

No real owner per-video data committed. No secrets, scraping, external API connection, publishing, scheduling, feature activation or automated changes to channel weights.

Run offline tests: \`python -m unittest tools.autoposter.tests.test_metricool_posts\`.
