# Open-source release guide

This project can be published as an open-source collector and reporting
pipeline, but the repository needs to separate code, configuration, and collected
content.

## What can be open sourced

- Source code, prompts, schemas, launchd templates, and local setup scripts:
  covered by this repository's MIT license.
- Source lists and scoring profiles: disclosed in `config/accounts.json` and
  `config/external_sources.json`.
- Generated report Markdown and article metadata: safe default for public
  archives when it contains links, summaries, extracted facts, and attribution.

## What needs separate rights

Collected article bodies, paid newsletter text, podcast transcripts, images, and
site-provided HTML are not covered by this repository's MIT license. Keep the
default export mode unless every upstream source is either explicitly licensed
for republication or you have separate permission.

The exporter enforces this distinction:

```bash
bin/iread export --output-dir public/archive
```

This writes:

- `sources.json`: disclosed sources and feed URLs.
- `articles.jsonl`: article metadata, original links, topics, summaries, facts,
  viewpoints, and quality scores.
- `reports.json`: generated report index.
- `manifest.json`: export policy and counts.

Full-text export requires an explicit confirmation flag:

```bash
bin/iread export \
  --output-dir public/archive-full \
  --include-content \
  --rights-confirmed
```

Use that only for sources you are allowed to republish.

## GitHub publishing checklist

1. Run the tests.

   ```bash
   python -m unittest discover -s tests -p 'test_*.py'
   ```

2. Check that secrets and local data are not tracked.

   ```bash
   git status --short
   git check-ignore .env data/research.db logs/pipeline.log
   ```

3. Export a public archive if you want to maintain data in the repository.

   ```bash
   bin/iread export --output-dir public/archive
   ```

4. Review the generated archive before committing it. The default archive should
   not contain `content_text` or `content_html`.

5. Publish the repository with `LICENSE`, `NOTICE.md`, `CONTRIBUTING.md`, this
   guide, the iRead subscription issue form, and the source configuration files
   included.

## Automation model

For WeChat collection, run the collector on a trusted local machine because it
depends on an authenticated WeChat session. A public GitHub Action is a poor
place for that session and the related secrets.

The local macOS launchd and Linux cron installers refresh the metadata-only
archive every day at 19:00. They intentionally do not commit or push the archive:
publishing to GitHub must be enabled separately by the repository owner after
reviewing the export and configuring narrowly scoped credentials.

For RSS-only subscriptions, a scheduled GitHub Action can run `sync`, `enrich`, and
`export` if the required model credentials and publisher terms allow it. Keep
full-text export disabled unless publication rights are confirmed.
