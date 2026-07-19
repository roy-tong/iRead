# Configure Research Fields

Accept one or more arbitrary fields from the conversation. Do not require the user to know sources, authors, RSS URLs, or taxonomy. Ask only for distinctions that materially change source selection, such as geography, audience, or explicit exclusions.

## Proposal

For every field:

1. Expand it into 3-8 durable topics and relevant event types.
2. Research at least eight sources covering primary evidence, independent reporting, specialist analysis, expert practice, and discovery-only signals.
3. Verify each source against its official homepage or profile. Verify two direct representative-work URLs per source.
4. Mark capture as `rss` only after verifying the feed. Otherwise use `web`, `api`, `wechat`, or `manual` and preserve the limitation.
5. Score all cold-start dimensions conservatively. Preserve commercial conflicts, uncertainty, collection limits, missing role coverage, and `web_pending` gaps.
6. Write one strict proposal JSON per field under `data/onboarding/<batch-id>/proposals/`, following the schema returned by `scripts/iread capabilities`.
7. Run `scripts/iread validate-proposal <proposal.json>` and fix failures before review.

Report progress before each field and after each validated proposal. Preserve completed artifacts when another field fails.

## Review And Approval

Show a compact topic and coverage summary, followed by source name, role, homepage, capture method, score, conflict or warning, and representative works. Explain the practical difference between `light`, `standard`, and `deep` reports.

Ask for the exact fields to approve, one shared report preset, and separately whether to start collection and recurring reports. Do not infer approval from praise or silence. Do not use blanket approval unless the user explicitly approves every field.

Create the manifest and run `apply-subscription` only for approved field IDs. Confirm the subscription appears in `workspace`. Starting collection requires a separate approved `activate --approved --install-schedule` operation with a stable request ID.

If WeChat authorization is required, show the local QR path. Never request cookies, tokens, passwords, licenses, or QR screenshots. Offer RSS/web-only degraded mode only after explicit confirmation. Required unresolved web sources must remain visible as `active_with_gaps`.
