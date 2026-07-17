# Source quality and representative works

Source review is profile-specific. A source can be authoritative for one type of
claim and unhelpful for another, so the system does not treat popularity as a
global truth score.

Run a review for the active profile:

```bash
bin/iread sources-review --output data/source-review.json
```

Each source receives four separate outputs:

- `domain_fit`: relevance to the active `profile.json` and topic taxonomy.
- `content_quality`: evidence, credibility, originality, and clickbait risk.
- `collection_quality`: connector availability, recency, body coverage, and
  archive depth.
- `confidence`: the number of analyzed articles supporting the observed score.

Configured source profiles are priors. Article-level observations gradually
replace those priors as the analyzed sample grows. The default policy treats 5
analyzed articles as medium confidence and 20 as high confidence. A high grade
with low confidence therefore remains provisional.

The output also selects representative works. It includes a high-quality sample,
a recent sample, and an originality-oriented sample when distinct articles are
available. Users should review these works before accepting a recommended source.

Rating weights, confidence thresholds, grades, and target source roles are
configured in `config/source_policy.json`. The source portfolio should cover a
mix of primary sources, expert voices, independent reporting, specialist
analysis, and discovery signals instead of selecting sources by score alone.
