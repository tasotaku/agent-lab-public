# agent-lab public core rules

## Outcome and scope

- State the intended outcome and observable success condition before substantial work.
- Resolve ambiguity only when different interpretations materially change the result.
- Keep edits inside the requested scope and preserve unrelated user changes.
- Ask before destructive, public, paid, permission-changing, or otherwise hard-to-reverse actions.

## Implementation

- Prefer the smallest design that satisfies the current requirement.
- Keep input, output, external I/O, failure boundaries, and non-goals explicit.
- Use clear names, shallow control flow, and comments that explain intent rather than syntax.
- Do not add speculative abstractions or dependencies.

## Verification

- Inspect the actual changed surface before claiming completion.
- Run relevant static checks and tests; add a focused test when behavior is not covered.
- For UI or generated artifacts, inspect the delivered result in the user's real surface.
- Report PASS, FAIL, or UNKNOWN from observed evidence, never from implementation intent.

## Safety and privacy

- Never commit credentials, customer data, conversations, private knowledge, or machine state.
- Keep authentication and trust prompts as explicit user-controlled steps.
- Back up existing configuration before replacement and make setup idempotent.
- Prefer public, reproducible dependencies and document anything that remains machine-local.

