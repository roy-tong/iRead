# Custom iRead subscriptions

The maintainer's example subscription tracks AI applications, embodied intelligence, and AI
hardware together. The recommended path for another set of fields is to create a
multi-domain manifest, run `batch-propose`, review the results, and run
`apply-subscription`. The generated directory contains one database and one report
stream for every approved domain.

Use separate configuration directories only when the user wants completely
independent subscriptions, schedules, and databases:

```bash
mkdir -p profiles/my-field
cp config/accounts.json profiles/my-field/accounts.json
cp config/external_sources.json profiles/my-field/external_sources.json
cp config/profile.json profiles/my-field/profile.json
cp config/source_policy.json profiles/my-field/source_policy.json
cp config/topics.json profiles/my-field/topics.json
cp config/reporting.json profiles/my-field/reporting.json
cp config/entities.bootstrap.json profiles/my-field/entities.bootstrap.json

bin/iread --config-dir profiles/my-field init
```

Missing files fall back to the repository `config/` directory, so a small profile
can override only the files it needs.

Subscriptions created by `apply-subscription` contain `subscription.json` and
`runtime.json`. The latter assigns separate `data/profiles/<id>` and
`logs/profiles/<id>` directories so different subscriptions do not mix. Explicit
`IREAD_DATA_DIR` and `IREAD_LOGS_DIR` environment variables override these values;
the old `REPORTER_*` names remain compatibility aliases.

## Target research fields

Edit `profile.json` first. This file describes the user intent that should remain
stable even when the topic taxonomy changes:

- `name` and `description`: the profile shown by the CLI, reader, and reports.
- `seed_keywords`: the short industry or field description supplied by the user.
- `audiences`: intended readers such as researchers, operators, or investors.
- `goals`: material changes, trend detection, verification, or other decisions.
- `languages`, `regions`, and `exclusions`: collection and analysis boundaries.
- `domains`: the approved top-level fields and their second-level topic ids.

Edit `topics.json` to define the taxonomy used for enrichment and reporting:

- `topics[].name`: the primary buckets shown in reports.
- `secondaries`: subtopics used for trend aggregation.
- `keywords` and `cross_cutting_keywords`: routing hints for classification.
- `event_keywords`: domain-specific events such as financing, product launches,
  papers, policy updates, or hiring changes.

After changing topics, run a small enrichment batch before trusting the reports:

```bash
bin/iread --config-dir profiles/my-field enrich --max-batches 1
bin/iread --config-dir profiles/my-field report daily --no-publish
```

## Target authors and feeds

Use `accounts.json` for WeChat public accounts:

```json
{
  "name": "Example Author",
  "wechat_id": "example_author_id",
  "priority": "required",
  "aliases": ["Example"]
}
```

Use `external_sources.json` for RSS, Atom, newsletters, blogs, podcasts, and
first-party publication feeds:

```json
{
  "id": "example-author",
  "name": "Example Author",
  "priority": "required",
  "source_type": "independent_practitioner",
  "homepage_url": "https://example.com/",
  "feed_url": "https://example.com/feed.xml",
  "capture_method": "rss",
  "content_mode": "summary_or_link"
}
```

`content_mode` should describe what the upstream feed allows or provides. Prefer
`summary_or_link` for feeds that do not clearly allow republication of full text.

After collecting and analyzing a sample, generate a source review:

```bash
bin/iread --config-dir profiles/my-field sources-review \
  --output data/my-field/source-review.json
```

The review separates domain fit, content quality, collection quality, and rating
confidence. It also provides representative works for user confirmation. Rating
weights and confidence thresholds live in `source_policy.json`.

## Report strategies

The `daily`, `weekly`, and `monthly` sections in `reporting.json` support:

- `enabled`: whether the scheduled report runs.
- cadence fields such as `publish_hour`, `weekday`, and rolling window size.
- `reading_minutes`: the intended reading budget.
- `focus`: report goals such as new evidence, trend change, or prediction review.
- `max_articles`: the maximum candidate set before event-level ranking.

The report prompt creates topic sections from `topics.json`; it no longer assumes
an AI-specific report outline.

## Local data separation

Profiles can use separate data and log directories through `.env`:

```text
IREAD_CONFIG_DIR=profiles/my-field
IREAD_DATA_DIR=data/my-field
IREAD_LOGS_DIR=logs/my-field
```

This override is useful for custom deployment layouts. Generated profiles are
already isolated through `runtime.json`; hand-built profiles should add that file
or set these variables to avoid mixing article databases and reports.
