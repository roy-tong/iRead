# Security Policy

Report security issues privately to the repository maintainer.

Do not open a public issue containing:

- Notion tokens or parent page IDs.
- We-MP-RSS usernames, passwords, secret keys, cookies, or QR login artifacts.
- Local database files from `data/`.
- Full article archives that may contain private, paid, or otherwise restricted
  content.

The project is designed for local collection first. Treat `.env`, `data/`,
`.runtime/`, and `logs/` as private runtime state.
