# Instagram profile, carousel and Stories previews

These modules adapt the useful principles from `ig-profile`, `ig-carousel` and
`ig-story` in
[`Jakeschincariol/instagram-agent-skill`](https://github.com/Jakeschincariol/instagram-agent-skill)
for SpecAvtoPortal. The upstream repository is MIT licensed (copyright 2026
Jake Schincariol). The application code, Russian copy rules, schemas, visual
renderer and tests here are original adaptations; the upstream instruction
files are not installed as runtime code.

All capabilities are offline-first, advisory and disabled by default:

```text
INSTAGRAM_FORMATS_ENABLED=0
```

They do not edit an Instagram profile, schedule content, call Instagram,
Buffer or YouTube, send messages, use paid services, or touch publication
state.

## Profile audit

`src/formats/profile.py` implements the complete upstream 12-criterion,
100-point rubric. It accepts the handle, name, bio, one website destination,
Highlights, pinned publications and nine grid-cover descriptions. Optional
photo, category/contact, activity and Story fields allow the remaining rubric
items to be verified. Missing inputs score only the evidence actually supplied
and mark the result `partial_unverified`; an indicative total is never labeled
fully verified.

The audit proposes three names and three bios. Bios use Instagram's documented
150-character limit. The name limit remains the conservative 30 characters
specified by the upstream rubric because Meta does not publish a stable number
for that field; the owner must confirm the live edit-screen counter before
applying a proposal.

## Carousel

`src/formats/carousel.py` consumes an owned article snapshot and reuses the
Growth Intelligence extraction and exact-statement validator. Three meaningful
source sentences are the minimum. The planner returns 6–10 slides: cover,
standalone second slide, exact evidence slides, recap and one CTA. Syndication
boilerplate is excluded. Thin sources produce no rendered deck.

The Pillow renderer creates 1080×1350 PNG files, 120-pixel safe margins,
source attribution, alt text, caption, contact sheet and machine-readable
resolution/overflow/readability checks. Rights-confirmed local PNG/JPEG article
images are accepted explicitly and rendered beneath a readability overlay.
Unconfirmed or unavailable files are rejected. The current demonstration
deliberately uses brand graphics only and fabricates no vehicle photographs.

Concise visible copy is never produced by cutting a sentence at a word count.
Each headline, body and recap line must match an explicit editorial mapping to
an exact original-source excerpt and reviewed Russian translation. Missing
mappings return `editorial_review_required`; changed numbers, qualifications or
technical terms fail validation.

For the BPW demonstration, the original article and BPW's official product
materials identify the component as `hub cap` (German `Radkapsel`). The review
manifest therefore uses the established Russian parts term `крышка ступицы`,
retains `hub cap` beside it, and rejects `колпачок концентратора прицепа`.

## Stories

`src/formats/story.py` uses the same evidence boundary and produces 3–7
1080×1920 frames. Text stays between y=250 and y=1600. The first frame is an
exact supported claim and the sequence contains one website action. A link
sticker is returned only as a manual editor instruction; the static PNG never
pretends that a sticker is functional. No comments, DMs or responses are sent.

## Generate review artifacts

```text
python tools/autoposter/scripts/instagram_formats_preview.py \
  --output tools/autoposter/previews/instagram_formats
```

The demo uses:

- an explicitly fabricated profile fixture;
- the existing repository-owned BPW article snapshot;
- no external or generated imagery.

Review `factual_qa.json`, each format's `visual_qa.json`, the attribution
manifests and `safety_manifest.json` before considering any manual use.

## Rollback

Leave `INSTAGRAM_FORMATS_ENABLED=0` and stop invoking the preview script. The
modules are not imported by the live Short Generator v2 or publishers, so no
state migration, schedule change or credential rollback is required.
