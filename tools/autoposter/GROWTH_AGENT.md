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
Growth Agent changes trigger an isolated job in the existing full-QA workflow.
The job runs with Growth Agent, paid AI and state mutation disabled, then
uploads the review bundle as a build artifact.
Keep the review pull request in draft until the owner has inspected that bundle.

## Natural Russian narration (review-only)

The human-quality voice path is separately disabled by default:

```text
NATURAL_VOICE_ENABLED=0
```

When enabled in an isolated preview, it prepares a spoken-only Russian form,
synthesizes the entire storyboard with one voice and maps Edge word boundaries
back to scene transitions. Storyboard facts, visible supporting copy and social
captions are never rewritten. A failed continuous synthesis blocks the preview;
it cannot silently mix Edge, OpenAI and gTTS between scenes. The old scene-based
path remains unchanged when the flag is off, including for SAT, test-drive and
guide modes.

Profiles live in `config/voice_profiles.json`; brand and technical
pronunciations live in `config/pronunciation_ru.json`. The initial free
recommendation is `edge_svetlana_professional` at `-2%`. The slower comparison
`edge_svetlana_deliberate` uses `-7%`. `edge_dmitry_conversational` remains
configured, but Dmitry returned no audio during the current availability check
and is not substituted silently. The optional OpenAI profile is never
called unless all of `NATURAL_VOICE_ENABLED=1`, `OPENAI_TTS=1`, a key, and the
separate owner-approval gate `ALLOW_PAID_TTS=1` are present.

Generate the nonpublishing listening bundle with:

```text
python tools/autoposter/scripts/voice_preview.py --output /tmp/natural-russian-voice
```

It produces three labeled 15-25 second MP3s: the current production-shaped
Svetlana `+5%` scene-reset baseline, continuous Svetlana at `-2%` with prepared
speech, and a slower `-7%` continuous comparison. `voice_comparison.json` records exact settings,
duration, substitutions, cost assumptions, requirements and known weaknesses.
The Full QA preview job also renders three complete Growth MP4s with the
recommended profile and uploads them in the same owner-review artifact. No
publisher, production state, secret or paid endpoint is touched.

## Reference and licensing

Design principles were adapted from the `ig-reel`, `ig-human`, `ig-caption`
and `ig-plan` skills in `Jakeschincariol/instagram-agent-skill` (MIT License,
copyright 2026 Jake Schincariol). The implementation here is original and
Russian/pipeline-specific; no source file was copied. The reference repository
was reviewed for hook alternatives, early relevance, single-CTA captions,
humanization heuristics and recent-topic avoidance.

## Rollback

Set `NATURAL_VOICE_ENABLED=0` (or remove it) to restore the exact legacy voice
selection/fallback path. Set `GROWTH_AGENT_ENABLED=0` (or remove it) to restore
the legacy storyboard, captions, topic score and output set. Neither rollback
requires a migration or state change.
