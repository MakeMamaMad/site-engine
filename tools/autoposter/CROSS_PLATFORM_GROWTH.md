# Cross-Platform Growth Optimization v1 — preview-only modules

Measures YouTube Shorts, Instagram Reels and TikTok performance of the same
underlying video, proposes source-grounded platform packaging, and flags weak
video openings. Everything is offline, advisory and disabled by default:

```text
CROSS_PLATFORM_GROWTH_ENABLED=0
```

No module publishes, schedules, logs in, scrapes, calls a paid API, changes
Buffer/YouTube/TikTok/Instagram integrations, production selection weights,
voice defaults, existing feature flags or secrets. `src/main.py` and
`src/v2_main.py` do not import this package.

Code: `src/crossplatform/`

| Module | Purpose |
|---|---|
| `analytics.py` | CSV/JSON ingestion, validation, duplicates/updates, explicit-ID matching, equal-window comparison, per-platform baselines, Markdown/JSON report |
| `hooks.py` | Distinct YouTube / Instagram / TikTok hook, title/caption and CTA from one approved article, with evidence for every factual statement |
| `visual_qa.py` | Multi-frame visual gate (black/blank openings, low variation, title region, overflow, aspect ratio/resolution, corrupt files) + contact sheet |
| `pipeline.py` | Feature flag and a read-only combined review |

## 1. Cross-platform analytics

### Input (CSV or JSON, one row = one metric snapshot)

Required:

| Field (aliases) | Notes |
|---|---|
| `content_id` (`article_id`, `canonical_content_id`, `source_id`) | The only key used to match platforms. No fuzzy/title matching. |
| `platform` | `youtube`, `instagram`, `tiktok` (aliases `yt`, `ig`, `tt`, `shorts`, `reels`) |
| `post_id` and/or `post_url` | URL host must belong to the platform; ID in URL must match `post_id` |
| `published_at` | ISO 8601 with timezone. Date-only allowed but then windows < 7d are not used |
| `collected_at` | ISO 8601 with time **and** timezone; must not precede `published_at` |
| `views` | Whole nonnegative number. `1.2K`, `12.5`, `1,234`, negatives are rejected |

Optional (left empty when not exported — never inferred): `engaged_views`
(YouTube only), `reach`, `watch_time_seconds` or `watch_time_hours`,
`average_watch_duration_seconds`, `average_percentage_viewed`,
`completion_rate` (`71%`, `71`, or `0.71` — the last is recorded as a
fraction conversion), `likes`, `comments`, `shares`, `saves`,
`followers_gained`, `profile_visits`, `website_clicks`, `dataset_label`.

### Rules

- Raw input rows are kept on every observation (`raw`); missing optional
  metrics are listed in `missing_metrics` and in per-platform coverage.
- Exact duplicate snapshots (same post and `collected_at`, same values) are
  removed once. Same post/time with different values are quarantined as
  `conflicting_snapshot`. A post mapped to two content IDs or two publication
  times is quarantined. Later snapshots are kept as updates; decreasing
  counters are reported (`counter_decreased`).
- Standard windows: 24h, 72h, 7d, 28d post age, tolerance `max(3h, 15%)`.
  Cross-platform comparison uses the largest window for which every platform
  has a snapshot. If none exists: `window_mismatch`, no comparison. A
  publication gap > 24h is warned.
- Raw views are never ranked across platforms (definitions differ). Each
  post is expressed as a ratio to **its own platform's** median at the same
  window, and only when that platform has ≥ 5 posts at that window.
- `engaged_views` exists only for YouTube; on other platforms the field is
  ignored (kept in `raw`) and it never appears in a cross-platform comparison.
- Descriptive observations and noncausal hypotheses are separate lists;
  hypotheses are always `not_causal_evidence: true`, confidence `low`.
- Website traffic is not attributed. Only platform-reported link clicks are
  listed.
- The owner's manual snapshot (YouTube 70 subscribers / +25 / 32 200 views in
  28 days; Instagram 4 followers / 71 posts; TikTok 1 follower / ~65–79 views)
  is attached as `owner_baseline_context`, classified
  `manual_owner_snapshot_not_comparable`, and is not merged into the dataset.

## 2. Platform-specific hooks

Input: article JSON with `title`, `source_url`, `summary`/`content`,
`editorial_status: "approved"`, `verified_facts` (exact source sentences),
optional `hashtags`; optionally a storyboard and `candidate_rewrites`.

| Platform | Packaging |
|---|---|
| YouTube Shorts | Hook = most specific numeric fact; title = exact source headline (≤100 chars, never truncated); description = fact list + source link + subscribe CTA |
| Instagram Reels | Hook = practical/mechanism fact; caption = hook + verified numbers as a list + source + save CTA + supplied hashtags |
| TikTok | Hook = shortest current complete fact; caption = headline + comment prompt; no site promotion |

Safety:

- Every factual statement is a whole source sentence that the owner listed
  as verified and that passes the Growth Intelligence validator
  (`validate_supported_statement`, `_safe_hook`). Sentences are never cut.
- Excerpt tails ending in `...`/`…`/`[...]` are excluded from evidence.
- Emotive or dated sentences ("гигантской", "Летом…") are not used as hooks.
- Rewrites (storyboard overlays, editor hooks) are validated with the
  Growth Agent semantic checks and reported as `validated_extractive` or
  `editorial_review_required`; they are never applied automatically.
- Unapproved source, missing `verified_facts`, overlong headline or no safe
  hook → `editorial_review_required`, confidence `low`.
- Every package is `approval_status: pending_owner_approval`. No paid model
  calls. Production narration and rendered videos are not changed.

## 3. Visual quality gate

`run_visual_qa(video=... | frames_dir=..., output_dir=...)`:

- ffprobe: missing/empty file, unreadable stream, aspect ratio (9:16 ± 1%),
  resolution (< 720 wide = error, < 1080 = warning);
- samples 6 opening frames (0–2 s) + 8 spread frames; at least 6 decodable
  frames are required — one good frame never passes;
- ffmpeg `blackdetect` over the whole video gives exact black intervals;
- a frame is `near_black` only if it is dark **and** has no detail
  (entropy/edges); dark detailed footage is `dark_but_detailed`, not black;
- the renderer's 0.18 s fade-in (black first frame only) is reported as
  information, not an error;
- title region (short_v2 layout) presence and contrast in the opening,
  side-margin overflow, near-identical frames across the whole video;
- `check_text_layout()` runs the renderer's own font and wrapping to detect
  overlay text that would be truncated;
- writes a JSON report and a small JPEG contact sheet. Always
  `approved_for_publication: false`; nothing is replaced or published.

## Run

```text
python -m unittest tools.autoposter.tests.test_cross_platform_growth
python tools/autoposter/scripts/cross_platform_preview.py --output /tmp/xp
```

CI: `.github/workflows/cross_platform_growth_preview.yml` (pull requests that
touch these files, or manual). Installs only Pillow + ffmpeg, keeps the flag
at 0, verifies labels/safety fields, rejects kept videos and caps the
artifact at 1 MB.

Committed sample outputs: `previews/cross_platform/`.

## Real data still required

1. **YouTube Studio export** per Short: video ID, publish time with timezone,
   collection time, views, engaged views, watch time, average view duration,
   average percentage viewed, likes, comments, shares, subscribers gained —
   ideally snapshots at ~24h, 72h, 7d and 28d.
2. **Instagram Insights export** per Reel (owner account): permalink, publish
   and collection times, views, reach, likes, comments, shares, saves,
   follows, profile visits, website/link clicks, average watch time.
3. **TikTok Analytics export** per video: video ID/URL, times, views, likes,
   comments, shares, saves, average watch time, watched-full-video rate,
   followers gained, profile views.
4. **Content-ID mapping**: the article ID (`frontend/data/news.json` `id`)
   for every post on every platform. Without it nothing is matched.
5. At least 5 posts per platform per window before relative indexes are
   produced; more for any hypothesis.
6. Owner approval of the article(s) used for packaging and of the
   `verified_facts` list.
7. Existing production MP4s (or extracted frames) to run the visual gate on
   real output.
8. Site analytics with UTM-tagged links if website attribution is ever
   wanted — not used or inferred here.
