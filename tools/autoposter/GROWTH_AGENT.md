# Instagram Growth Agent v1

Growth Agent is an optional quality and factual-safety layer for news shorts.
It is disabled by default:

```text
GROWTH_AGENT_ENABLED=0
```

Set the value to `1` only in a preview or approved production environment. The
flag affects news topic ranking, hook selection, Russian text normalization,
factual validation and platform captions. SAT, test-drive and guide modes keep
their existing hand-authored storyboards. Publication schedules, Buffer and the
YouTube uploader are unchanged.

When enabled, `out_v2/growth_report.json` records up to three complete hook
candidates, the selected hook, source URLs and deterministic validation
results. Hard factual failures and nonblocking quality warnings are reported
separately. If AI output contains an unsupported or contradicted claim, it is
rejected and replaced by the source-only deterministic storyboard. If the
source itself cannot support a distinct hook plus at least two factual beats,
generation stops before rendering or publication and writes a rejected report.

Run the deterministic tests and comparison generator with Python 3.11:

```text
py -3.11 -m unittest tools.autoposter.tests.test_growth_agent
py -3.11 tools/autoposter/scripts/growth_preview.py
python tools/autoposter/scripts/growth_preview.py --render --output /tmp/growth-agent-review
```

The comparison generator never calls a publisher. It writes three old/new
cases plus an advisory content plan under
`tools/autoposter/previews/growth_agent_v1/`. With `--render`, it also creates
six MP4 files, contact sheets and ffprobe/visual QA reports. The dedicated
`growth_agent_review_preview.yml` workflow runs with Growth Agent, paid AI and
state mutation disabled, then uploads the review bundle as a build artifact.

## Reference and licensing

Design principles were adapted from the `ig-reel`, `ig-human`, `ig-caption`
and `ig-plan` skills in `Jakeschincariol/instagram-agent-skill` (MIT License,
copyright 2026 Jake Schincariol). The implementation here is original and
Russian/pipeline-specific; no source file was copied. The reference repository
was reviewed for hook alternatives, early relevance, single-CTA captions,
humanization heuristics and recent-topic avoidance.

## Rollback

Set `GROWTH_AGENT_ENABLED=0` (or remove it). The legacy storyboard, captions,
topic score and output set are then used without a migration or state change.
