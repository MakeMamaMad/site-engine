# Cross-platform performance report

> Dataset labels: synthetic_cross_platform_fixture_not_real. Advisory only; nothing is published or reweighted.

Rows: 62 · accepted snapshots: 56 · rejected: 3 · exact duplicates removed: 1 · conflicts quarantined: 1 · posts: 21 · content items: 8

## Per-platform baselines (views, within platform only)

| Platform | Posts | 24h median (n) | 72h median (n) | 7d median (n) | 28d median (n) |
|---|---:|---:|---:|---:|---:|
| youtube | 8 | 500 (7) | 977 (5) | 1150 (7) | — |
| instagram | 6 | 32 (6) | 50 (6) | 59 (6) | — |
| tiktok | 7 | 38.5 (6) | 59.5 (6) | 70.5 (6) | — |

Metric definitions differ: **youtube** — YouTube Shorts views as exported from YouTube Studio. Since 2025 Shorts views count plays/replays; this is not the same definition as Instagram or TikTok views. **instagram** — Instagram Reels views as shown in owner-exported Insights. Definition is Instagram's own and is not equivalent to YouTube or TikTok views. **tiktok** — TikTok video views as shown in owner-exported analytics. Definition is TikTok's own and is not equivalent to YouTube or Instagram views.

## Cross-platform matching (explicit content IDs)

| Content ID | Status | Window | Relative to own platform median | Notes |
|---|---|---|---|---|
| art-001 | matched_all_three | 7d | instagram: 1.02x, tiktok: 0.99x, youtube: 0.78x | — |
| art-002 | matched_all_three | 7d | instagram: 0.76x, tiktok: 0.94x, youtube: 1.22x | — |
| art-003 | matched_all_three | 7d | instagram: 2.37x, tiktok: 1.06x, youtube: 0.54x | — |
| art-004 | matched_all_three | 7d | instagram: 1.19x, tiktok: 3.40x, youtube: 1.83x | — |
| art-005 | matched_all_three | 7d | instagram: 0.88x, tiktok: 0.96x, youtube: 0.70x | — |
| art-006 | matched_all_three | 7d | instagram: 0.98x, tiktok: 1.01x, youtube: 1.00x | — |
| art-007 | partial_match | none | — | publication_time_gap, window_mismatch |
| art-008 | single_platform | none | — | — |

## Descriptive observations

- youtube: median views at 24h = 500 across 7 posts
- youtube: median views at 72h = 977 across 5 posts
- youtube: median views at 7d = 1150 across 7 posts
- instagram: median views at 24h = 32 across 6 posts
- instagram: median views at 72h = 50 across 6 posts
- instagram: median views at 7d = 59 across 6 posts
- tiktok: median views at 24h = 38.5 across 6 posts
- tiktok: median views at 72h = 59.5 across 6 posts
- tiktok: median views at 7d = 70.5 across 6 posts
- art-001 at 7d: instagram 1.02x own median, tiktok 0.99x own median, youtube 0.78x own median
- art-002 at 7d: instagram 0.76x own median, tiktok 0.94x own median, youtube 1.22x own median
- art-003 at 7d: instagram 2.37x own median, tiktok 1.06x own median, youtube 0.54x own median
- art-004 at 7d: instagram 1.19x own median, tiktok 3.40x own median, youtube 1.83x own median
- art-005 at 7d: instagram 0.88x own median, tiktok 0.96x own median, youtube 0.70x own median
- art-006 at 7d: instagram 0.98x own median, tiktok 1.01x own median, youtube 1.00x own median

## Noncausal hypotheses (require testing)

- Packaging or audience fit may differ: instagram outperformed its own median while youtube underperformed. One item cannot establish a cause. Test: Repeat with several matched items and alternate hook/caption variants per platform before drawing conclusions.

## Website traffic

- Only platform-reported link clicks are listed. Site visits are not attributed to any platform or video.

## Data warnings

- `publication_time_gap` art-007 — Platforms published at different times; audience/day effects differ.
- `window_mismatch` art-007 — No standard window (24h/72h/7d/28d) has a snapshot for every platform; no cross-platform comparison is made.

## Rejected rows

- row 60: views: count must be a whole number without abbreviations or separators, got '1.2K'
- row 61: collected_at is earlier than published_at
- row 62: published_at: timezone offset required (e.g. +03:00 or Z): '2026-10-20 10:00:00'; views: cannot be negative, got '-5'

## Quarantined conflicts

- `conflicting_snapshot` youtube:YTs01abcde rows [2, 59]

## Owner-supplied snapshot (context only, not part of the dataset)

- YouTube: 70 subscribers, +25 in 28 days, 32200 views in 28 days.
- Instagram: 4 followers, 71 posts.
- TikTok: 1 follower, recent visible videos around 65–79 views.

Not comparable because:
- Channel-level totals, not per-post observations with publication and collection timestamps.
- Different scopes: YouTube is a 28-day aggregate; Instagram is a lifetime post count; TikTok is a visual range of recent videos.
- No explicit content IDs link these numbers across platforms.
- Instagram/TikTok Insights (reach, watch time, completion) were not supplied and are not inferred.

## Limitations

- View definitions differ by platform; raw views are never ranked across platforms.
- YouTube engaged views are YouTube-only and are not compared with Instagram or TikTok views.
- Cross-platform statements use each post's ratio to its own platform median at an equal post-age window.
- Metrics absent from the import stay absent; nothing is estimated or inferred.
- Descriptive observations are not causal findings; hypotheses require controlled repeats.
