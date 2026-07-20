# Configure Research Fields

Accept one or more arbitrary fields from the conversation. Do not require the user to know sources, authors, RSS URLs, or taxonomy. Ask only for distinctions that materially change source selection, such as geography, audience, or explicit exclusions.

## Proposal

For every field:

1. Expand it into 3-8 durable topics and relevant event types.
2. Target 10-15 sources (minimum eight): at least two primary, two independent, one specialist, one expert/practitioner, and one discovery-only source. At least 35% and no fewer than three must be verified RSS or WeChat sources; generic APIs remain pending until a connector exists.
3. Verify each source against its official homepage or profile. Verify two direct representative-work URLs per source.
4. Mark capture as `rss` only after verifying the feed. Otherwise use `web`, `api`, `wechat`, or `manual` and preserve the limitation.
5. Score all cold-start dimensions conservatively. Preserve commercial conflicts, uncertainty, collection limits, missing role coverage, and `web_pending` gaps.
6. Write one strict proposal JSON per field under `data/onboarding/<batch-id>/proposals/`, following the schema returned by `scripts/iread capabilities`.
7. Run `scripts/iread validate-proposal <proposal.json>` and fix failures. Then run `scripts/iread review-proposal <proposal.json>` to create the complete clickable review artifact.

Report progress before each field and after each validated proposal. Preserve completed artifacts when another field fails.

## Review And Approval

In chat, show the topic and coverage summary plus at most five core sources per field. Link the generated `.review.md` for the complete source list, conflicts, warnings, and representative works; do not paste the whole artifact into chat. Explain the practical difference between `light`, `standard`, and `deep` reports.

Ask for the exact fields to approve, one shared report preset, and separately whether to start collection and recurring reports. Do not infer approval from praise or silence. Do not use blanket approval unless the user explicitly approves every field.

Create the manifest and run `apply-subscription` only for approved field IDs. Confirm the subscription appears in `workspace`. Starting collection requires a separate approved `activate --approved --install-schedule` operation with a stable request ID.

If WeChat authorization is required, show the local QR path. Never request cookies, tokens, passwords, licenses, or QR screenshots. Offer RSS/web-only degraded mode only after explicit confirmation. Required unresolved web sources must remain visible as `active_with_gaps`.
