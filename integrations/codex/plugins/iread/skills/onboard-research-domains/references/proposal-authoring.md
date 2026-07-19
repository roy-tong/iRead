# Current-Task Proposal Authoring

Generate proposals with the current Codex task and its web tools. Do not invoke a nested Codex process on the normal Codex path.

## Research sequence

1. Expand the user's field into 3-8 durable topics and relevant event types.
2. Build a role-balanced source set: first-party evidence, independent verification, specialist interpretation, practitioner voices, and discovery-only leads.
3. Verify every source against its own homepage or official profile. Search results and aggregators are discovery aids, not evidence URLs.
4. Verify 2-3 representative works per source with direct, openable URLs. Prefer durable examples over merely recent posts.
5. Confirm RSS/Atom URLs before setting `capture_method: rss`; otherwise use `web`, `api`, `wechat`, or `manual` and preserve the limitation in `warnings`.
6. Score conservatively on the 0-100 scale and state low confidence when evidence is sparse. Preserve institutional or commercial conflicts.
7. Write JSON that matches `schemas/research_proposal.schema.json`, include `proposal_version`, `generated_at`, and `request`, then validate it with `iread validate-proposal`.

## User review

Present a compact overview before detailed rows:

- domain and proposed topic map;
- total sources and counts by role/capture method;
- required coverage gaps and uncertain links;
- the practical difference between light, standard, and deep reports.

For each source show name, role, why it matters, capture method, preliminary composite score, conflict/warning, and representative-work links. Do not imply that a score is observed performance.

End with reply-ready choices. The user should be able to approve, remove a named source, change a field boundary, choose a report policy, and decide whether collection starts without learning CLI syntax.
