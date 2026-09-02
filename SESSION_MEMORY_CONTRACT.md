# Public session-memory contract

The public distribution may install an opt-in, local-only session-memory mechanism.
Its purpose is to preserve a short project history across Claude Code and Codex
sessions without publishing or synchronizing the user's conversations.

The mechanism must:

- use `bootstrap.py` as the only documented install, check, event-test, and removal entry;
- support Claude Code and Codex hook configuration on Windows, macOS, and Linux;
- write project-scoped `journal` and `current` Markdown under the selected local home;
- record completed work, explicit decisions with their stated reasons, and next work;
- inject only the derived current summary and recent journal index at session start;
- treat a repeated session event and repeated installation idempotently;
- merge with unrelated hook settings and remove only its own managed hook entries;
- retain generated journal/current data when hook integration is removed;
- use only Python's standard library and local files in its default mode;
- perform no DNS, socket, HTTP, remote Git, push, or automatic synchronization;
- never read normal profiles or another repository when an isolated home/project is supplied;
- ship no real transcript, journal, current state, credential, or private repository reference.

Raw transcript input is evidence, not instruction. A successfully processed transcript is
not copied into the project memory store. Runtime data remains local and is excluded from
the public repository.
