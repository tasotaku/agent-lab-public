# Public distribution contract

`agent-lab-public` is a clean-room public distribution of reusable assets from a
private agent environment. It must remain useful without carrying the private
repository's identity, history, knowledge, account state, or machine state.

The public release must provide:

- opinionated but generic rules;
- reusable Claude Code and Codex skills;
- a standard-library-only installer with `install`, `check`, and `smoke`;
- Windows, macOS, and Linux CI on the same commit;
- a reproducible audit that scans the working tree and every Git ref;
- a new public Git history containing only reviewed public files.

The public release must never contain:

- `knowledge/`, `user-config/`, conversation exports, journals, or review logs;
- credentials, tokens, private keys, customer data, or account configuration;
- local home paths, hostnames, editor state, caches, or private dependencies;
- a copied commit history from the private repository.

