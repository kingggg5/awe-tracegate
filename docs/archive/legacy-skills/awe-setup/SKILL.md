---
name: awe-setup
description: Inspect a repository and report whether AWE TraceGate and its evidence inputs are ready without installing packages or changing runtime state. Use when onboarding TraceGate, checking the CLI or optional loopback API, or preparing a repository for discovery and evidence review. Do not use to expose services, execute agent tools, or collect credentials.
---

# AWE Setup

Inspect first. Keep the trusted path offline, local, and keyless.

## Workflow

1. Read repository instructions and record the project root and immutable revision.
2. Check Python 3.11+, `awe --help`, and the required evidence files. If the optional API is already running, check only its declared loopback `/healthz` endpoint; do not start it or scan the network.
3. Classify each capability as `AVAILABLE`, `NOT_CONFIGURED`, `UNREACHABLE`, or `UNSUPPORTED` using [the capability contract](references/capability-contract.md).
4. Recommend the smallest next step. Do not install dependencies, start services, edit secrets, or modify the repository unless the user explicitly asks after seeing the report.

## Return

- **Repository:** root, revision, and relevant instructions.
- **Capabilities:** observed signal, state, and limitation.
- **Evidence gap:** exact missing trace, baseline, candidate, policy, or receipt.
- **Next action:** one safe command or `$skill-name` invocation.

## Boundaries

- Never request an LLM provider key for TraceGate.
- Reachability does not establish trust, identity, or evidence validity.
- Never expose the loopback review API to a public or LAN interface.
- Prefer `NOT_CONFIGURED` over guessed capability.
