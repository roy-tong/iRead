---
name: onboard-research-domains
description: Create one reviewed iRead subscription from one or more arbitrary research fields. Use for source discovery, representative works, or initial daily/weekly/monthly setup.
---

# Configure iRead Domains

Use `../../scripts/iread` relative to this file. Run only `workspace` first. Do not run Doctor, inspect the repository, rebuild indexes, or invoke another Codex process.

Accept one or more fields from the conversation. Ask only about geography, audience, or exclusions when they materially change source selection. Explain that iRead will research sources and stop for approval before collection.

For proposal research, read `references/batch-manifest.md` and `references/proposal-authoring.md`. Work in the current Codex task with current web tools. Run `iread validate-proposal` and `iread review-proposal` for every proposal, show at most five core sources per field in chat, and link the complete `.review.md`. End with exact reply choices such as `批准全部领域，使用标准报告，开始采集`. Stop until approval is explicit.

Only after approval, read `references/apply-and-activate.md`. Run `capabilities` once before the first mutation. Use stable request IDs, apply only approved domain IDs, and require separate collection/schedule consent. After mutations, run `workspace` and `acceptance`; disclose every warning and required coverage gap.
