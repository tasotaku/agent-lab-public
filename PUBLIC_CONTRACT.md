# Public distribution contract

`agent-lab-public` is a clean-room public distribution of reusable assets from a
private agent environment. It must remain useful without carrying the private
repository's identity, history, knowledge, account state, or machine state.

The public release must provide:

- opinionated but generic rules;
- reusable Claude Code and Codex skills;
- a standard-library-only installer with `install`, `check`, and `smoke`;
- an opt-in, standard-library-only session-memory mechanism that stores derived notes locally;
- Windows, macOS, and Linux CI on the same commit;
- a reproducible audit that scans the working tree and every Git ref;
- a new public Git history containing only reviewed public files.

The public release must never contain:

- real or generated runtime `knowledge/`, `user-config/`, conversation exports, journals, or review logs
  (generic mechanism code and explicit synthetic test fixtures are allowed);
- credentials, tokens, private keys, customer data, or account configuration;
- local home paths, hostnames, editor state, caches, or private dependencies;
- a copied commit history from the private repository.
