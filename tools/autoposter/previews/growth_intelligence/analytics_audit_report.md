# Instagram analytics audit — synthetic fixture

> All metrics in this report are synthetic test data, not real SpecAvtoPortal audience performance.

Posts: **12**. Median views: **12000**. Range: 2026-09-01 to 2026-10-15.

## Top posts relative to the account median

| Post | Multiple | Views | Reach | 3s retention | Shares/reach |
|---|---:|---:|---:|---:|---:|
| synthetic-01 | 3.50x | 42000 | 35000.0 | 76% | 1.20% |
| synthetic-02 | 2.58x | 31000 | 27000.0 | 71% | 1.04% |
| synthetic-03 | 2.17x | 26000 | 22000.0 | 67% | 0.86% |
| synthetic-04 | 1.83x | 22000 | 18500.0 | 64% | 0.86% |

## Observed metrics

- Imported posts: 12; median views: 12000.

## Descriptive patterns — not causal findings

- hook_formula **number_first**: median 2.38x, n=4.
- hook_formula **question**: median 1.00x, n=4.
- hook_formula **negative_command**: median 0.41x, n=4.
- content_topic **регламенты**: median 1.21x, n=4.
- content_topic **рынок**: median 1.08x, n=3.
- content_topic **эксплуатация**: median 0.75x, n=5.

## Hypotheses — not causal findings

- Higher three-second retention may be associated with above-median views in this sample. Confidence: low.

## Proposed experiments

- Run an owner-approved comparison using hook formula 'number_first' against the current baseline. Confidence ceiling: low; exploratory only: yes.

## Missing/partial data warnings

- `metric_partial` — non_follower_reach
- `small_sample` — Only 12 posts; conclusions are directional.

No missing reach, retention, follows or non-follower metrics were inferred.
