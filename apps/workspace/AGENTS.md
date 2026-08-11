# AWE Workspace contributor guide

## Product boundary

- This package is the local, human-gated runtime coordinator for AWE TraceGate.
- It may persist goals, discovery metadata, runtime approvals, handoffs, and
  checkpoints.
- It must not invoke models or tools, execute shell/browser actions, store
  provider credentials, promote candidates, or issue TraceGate decisions.
- Its data is untrusted input to the separate Python evidence boundary.

## Architecture

- `src/contracts.ts` owns versioned public data contracts and strict parsers.
- `src/store.ts` owns bounded, atomic, single-process local persistence.
- `src/server.ts` owns the loopback-only HTTP and static-file boundary.
- `web/` is dependency-free HTML, CSS, and JavaScript.
- The Python package under `../../src/awe_tracegate` must never import this app.

## Change discipline

- Prefer explicit actions and enums over natural-language intent inference.
- Keep every mutation same-origin and every network target loopback-only.
- Keep permissions narrow and descriptive; a handoff is not an authorization
  token.
- Preserve backward-compatible migrations for supported local store versions.
- Add normal, malformed, tampered-store, and state-transition tests for public
  contract changes.
- Do not duplicate the root Skills/plugin distribution inside this package.

## Verification

From this directory:

```bash
npm ci
npm run check
npm test
```

Also run the root Python and installer checks when changing the monorepo trust
boundary or shared documentation.
