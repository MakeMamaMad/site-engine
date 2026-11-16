# Calculator Shorts -> website: first offline conversion experiment

## Why

Metricool confirms short-form distribution but website conversion is not yet demonstrated.
Yandex Metrica overview for **1-16 Nov 2026** showed 136 visitors, 157 visits,
181 pageviews; the **social traffic** slice was **3 pageviews**, not 3 unique
visitors or 3 UTM visits. Search accounted for 124 pageviews in the overview.
These data are not a controlled experiment or proof of causal lift.

## Safety and rollout boundary

This PR adds **reviewable URL bundles only**, under
`src/crossplatform/calculator_campaign.py`, plus a CLI. No existing producer,
publisher, scheduler, caption, voice or social account is touched. No flag is
enabled, and no network or paid model is invoked. Do not infer view-to-site
conversion from rollup metrics.

Run from the repository root:

```bash
python -m tools.autoposter.scripts.calculator_campaign_preview --target axis_distribution --content-id axis_loading_01
python -m unittest tools.autoposter.tests.test_calculator_campaign
```

Allowed target keys:
- `axis_distribution` -> https://spec-avtoportal.ru/tools/raspredelenie-gruza-po-osyam/
- `axle_load` -> https://spec-avtoportal.ru/tools/nagruzka-na-os/
- `trip_cost` -> https://spec-avtoportal.ru/tools/stoimost-reysa/

Output has exact per-platform URLs, `utm_source` = youtube/instagram/tiktok,
`utm_medium=video`, `utm_campaign=calculator_short_202611` and
`utm_content` = a stable, owner-assigned lowercase ASCII content ID.
For the same underlying video, use the *same content ID* on all platforms.
Never invent a social post receipt from upload times or titles.

## Editorial experiment (14 days, at most 2 shorts/day)

Use ONLY site-verified, human-reviewed examples and numbers. Alternate:
1. "Как распределить груз между осями?" -> axis_distribution.
2. "Как проверить нагрузку на ось?" -> axle_load.
3. "Во сколько обходится рейс?" -> trip_cost.

Hook (first ~2s): a concrete question or simple example.
Middle: show input fields and actual output of the calculator, with
**verified input values**; no invented limits, fines, regulations, or tariffs.
CTA: "Проверьте свои данные в калькуляторе СпецАвтоПортала".
Use visual end card with legible tool name/brand.

**Instagram:** URL in a Reel caption is usually not clickable. Before claiming
tracked conversions, manually set and verify the active profile link (or
supported Story link sticker), and direct viewers there. Rotating the profile
link for each Reel makes post-level attribution unreliable; a stable landing
page with distinct clickable links is an alternative, but requires its own
review and testing. **TikTok:** check actual website/profile link availability.
**YouTube:** verify the clickable surfaces for this particular Shorts account;
do not assume all description links are clickable.

## Reporting and QA

In Yandex Metrica: Sources -> UTM tags; inspect `utm_campaign`,
`utm_source`, `utm_content`. Compare **visits** and **users**, independently
of pageviews and views on video platforms. Check landing pages, link taps,
bounce rate and engagement/goals where available.

Baseline should be a comparable 14-day period, with matched weekdays and
the same traffic definitions. Review visits at 24h, 72h, 7d after release.
Do not label directional data as a causal lift, particularly at low volume.
Stop/repair any broken link or misleading CTA immediately.

No published link, tagged website visit, or growth improvement is claimed
by producing this offline preview alone.
