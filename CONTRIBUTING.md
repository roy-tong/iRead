# Contributing

iRead welcomes code fixes, source corrections, report-policy improvements, and new domain or subscription proposals.

## Propose research fields

Use the GitHub subscription request form. One or more field names are enough to start; regions, languages, audiences, goals, exclusions, target authors, and known sources are optional. Maintainers or agents generate one proposal per field, review them separately, and combine approved fields with `apply-subscription`.

```bash
bin/iread propose --field "<research field>" --output data/proposal.json
```

Before accepting a profile, review direct source URLs, role coverage, conflict notes, warnings, feed validity, and representative works. Generated scores are cold-start priors and must not be described as observed quality.

## Source-list changes

Source additions should include:

- a stable name and first-party homepage;
- the source role and covered topics;
- a direct RSS, Atom, podcast, or API endpoint when one is verified;
- two or three representative works;
- known affiliations, commercial incentives, or other conflicts;
- collection and republication constraints.

Do not submit scraped credentials, paywalled copies, session cookies, or third-party article bodies. Links, metadata, short factual descriptions, and original analysis are the safe default.

## Code changes

Run the test suite before opening a pull request:

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall -q src tests
```

Keep profile-specific assumptions in configuration, prompts, or schemas rather than hard-coding them into shared pipeline code. New collection adapters must document their license and authentication boundary in `NOTICE.md` and `docs/disclosure.md`.
