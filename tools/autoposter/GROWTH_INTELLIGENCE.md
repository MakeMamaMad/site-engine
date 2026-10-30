# Instagram Growth Intelligence — preview-only modules

This package adapts three design references from
[`Jakeschincariol/instagram-agent-skill`](https://github.com/Jakeschincariol/instagram-agent-skill)
to SpecAvtoPortal's Python Growth Agent. It is application code, not an
installation of standalone ChatGPT or Codex Skills.

The entire pipeline is offline-first, advisory and disabled by default:

```text
GROWTH_INTELLIGENCE_ENABLED=0
```

No module schedules, publishes, logs into Instagram, scrapes accounts, changes
topic weights, reads private Insights or calls a paid service.

## What the references contributed

The upstream `ig-viral` skill contributed the principle that public examples
must be ranked by views divided by each account's own recent median, not by raw
views. The implementation in `src/intelligence/viral.py` adds strict CSV/JSON
validation, provenance, duplicate handling, Russian hook formulas, account and
sample-size thresholds, and original Russian recommendation templates. It does
not include the upstream browser workflow or a scraper.

The upstream `ig-repurpose` skill contributed extraction before format choice:
claims, numbers, mechanisms, practical points and attributed quotes are found
before deciding whether the source supports a Reel, carousel or Story. The
implementation in `src/intelligence/repurpose.py` retains exact evidence and
source URLs, validates the final suggested hook, never truncates a source
sentence into a new factual claim, rejects unsupported numbers, deduplicates
angles and returns no multi-format package for a thin article. Long or
incomplete hook candidates remain cited evidence with an explicit warning.

The upstream `ig-audit` skill contributed account-median normalization and the
separation of hook, distribution and conversion metrics. The implementation in
`src/intelligence/audit.py` calculates only fields present in owner-imported
CSV/JSON, reports coverage, distinguishes observed facts from noncausal
hypotheses, and warns when sample sizes are small. Its output explicitly
separates imported metrics, descriptive patterns, noncausal hypotheses and
owner-approved proposed experiments. Small or incomplete datasets cap
experiment confidence at low and never change production weights.

These adaptations use the upstream repository under its MIT License
(copyright 2026 Jake Schincariol). The application implementation and Russian
transport-specific schemas are original; upstream `SKILL.md` files and
`swipe.py` are not copied into the runtime.

## Inputs

### Viral-pattern dataset

CSV or JSON, manually curated. Required per row:

- `account`: public handle, for example `@account`;
- `source_url`: exact public Reel/Short URL;
- `views`: observed view count;
- `account_median_views`: median from a stated recent account sample;
- `hook`: first complete spoken or visible line;
- `dataset_label`: for example `manual_public_review_2026_10`.

Optional fields are `captured_at`, `length_seconds`, `cta`, `on_screen` and
`hook_formula`. The importer rejects missing provenance, nonpositive medians,
invalid URLs and invalid numeric values. Duplicate URLs or account/hook pairs
are ignored with warnings. No arbitrary competitor analytics are assumed to be
available.

### Repurposing source

JSON/dict with `title`, `source_url`, and at least one of `summary`, `content`
or an owned `transcript`. Optional fields: `source_name`, `published_at` and
`data_classification`. The source text itself is the evidence boundary.

### Analytics audit

CSV or JSON with `post_id` and `views`. Supported optional fields:

- `publication_date` in `YYYY-MM-DD`;
- `reach`, `shares`, `saves`, `follows`;
- `average_watch_time_seconds`;
- `three_second_retention` and `non_follower_reach` as `0.71` or `71%`;
- `content_topic`, `hook_formula`, `format`, `source_url`, `dataset_label`.

The current Buffer adapter exposes channel, publishing and post-status fields.
Its documented queries in this repository do not expose a complete Instagram
Insights dataset, so Buffer is not used to invent reach, retention, saves,
shares or follows.

## Run and outputs

Run all deterministic tests:

```text
python -m unittest tools.autoposter.tests.test_growth_intelligence
```

Generate the labeled demonstration reports:

```text
python tools/autoposter/scripts/growth_intelligence_preview.py \
  --output tools/autoposter/previews/growth_intelligence
```

The preview includes:

- `viral_pattern_report.{json,md}`;
- `repurposing_package.{json,md}`;
- `analytics_audit_report.{json,md}`;
- `recommendation_pipeline.json`.

All supplied fixtures are labeled synthetic and must never be presented as
real audience or competitor performance. The integrated pipeline maps evidence
to advisory content-plan suggestions but writes no schedule and changes no
selection weight.

## Future approved data sources

A future connector may call the existing pure functions after owner approval
if it can provide authenticated, documented per-post fields and retain a source
identifier, collection timestamp and data classification. Add the connector as
a separate importer; do not put credentials, network collection or publishing
inside the analysis modules. Public competitor examples should remain a small,
manual corpus unless the owner obtains an authorized data source with terms
that permit automated collection.

## Rollback

Keep or set `GROWTH_INTELLIGENCE_ENABLED=0`, or stop invoking the preview CLI.
The modules are not imported by the production renderer or publishers, so no
state migration or schedule change is required.
