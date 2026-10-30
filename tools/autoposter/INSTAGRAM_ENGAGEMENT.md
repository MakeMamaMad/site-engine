# Instagram engagement drafts

Offline adaptations of upstream `ig-comment`, `ig-reply`, and `ig-dm` from
[`Jakeschincariol/instagram-agent-skill`](https://github.com/Jakeschincariol/instagram-agent-skill),
used under its MIT License (copyright 2026 Jake Schincariol).

The modules only prepare drafts. `INSTAGRAM_ENGAGEMENT_ENABLED=0` by default;
there is no login, scraping, network call, scheduling, posting, reply, or DM send.
Every result requires human approval. Missing evidence or recipient context
returns `editorial_review_required`.

Run focused tests:

```bash
python -m unittest tools.autoposter.tests.test_instagram_engagement
```

Limitations: classification is deterministic keyword/rule triage, verified
answers must be supplied by the caller, and no Instagram state is inspected.
