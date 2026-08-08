# Security model

AWE Agent Harness is a pre-alpha, offline reviewer. Its safest useful boundary
is intentionally narrow: parse untrusted trace data, derive a read-only workflow
candidate when the evidence is sufficient, and otherwise refuse.

This document describes intended controls, not a certification or a production
security claim.

## Trust boundaries

Treat all of the following as untrusted:

- trace files and step outputs;
- tool names, descriptions, and model-authored text;
- paths supplied on the command line;
- receipts received from another machine;
- requests to the optional HTTP API.

Only typed validation, explicit compiler rules, and recomputed canonical hashes
belong to the decision boundary. Text inside a trace is data; it cannot rewrite
policy, grant a capability, approve a step, or change an effect class.

## v0 safety properties

- No LLM or external provider call is required or made by the compiler.
- No trace step is executed or replayed.
- Shell, browser, deployment, rollback, and arbitrary tool execution are absent.
- Write-like or unsupported effects are refused.
- Hard dependency edges require explicit, consistent bindings.
- Invalid, incomplete, or ambiguous evidence fails closed as malformed input or
  a typed refusal.
- A receipt hash can be recomputed offline.

## Important limitations

- SHA-256 integrity is not signer identity. Until a receipt is signed or anchored
  externally, call it content-addressed—not authenticated or tamper-proof.
- A `compiled` decision does not prove semantic correctness, policy compliance,
  usefulness, or production safety.
- Repeated successful traces may contain correlated mistakes or incomplete
  coverage. Compilation does not create missing branches or counterexamples.
- The local API is not an internet-facing deployment profile. It does not imply
  authentication, tenant isolation, rate limiting, or denial-of-service
  protection.
- Python process isolation is not a sandbox. AWE avoids executing trace content
  rather than claiming the host process contains hostile code.

## Sensitive data

Do not place credentials, access tokens, private source code, personal data,
customer payloads, or full production prompts in examples, issues, or public
receipts. Hashing a secret does not make publication safe: low-entropy values
may be guessed and metadata can still be sensitive.

Operators remain responsible for classifying, minimizing, redacting, retaining,
and deleting their trace data before AWE reads it. The project does not claim an
automatic PII or secret-redaction guarantee.

## API guidance

If you expose the optional API outside a developer machine, place it behind an
operator-owned control plane that supplies authentication, authorization,
request-size limits, timeouts, audit logging, TLS, and network policy. Never use
the health endpoint or a successful compile response as authorization for a
side effect.

## Dependency and release hygiene

- Pin released artifacts and review dependency changes.
- Run the test suite before release.
- Keep compiler decisions covered by golden and adversarial fixtures.
- Treat changes to schemas, canonicalization, effect classification, and refusal
  rules as security-sensitive.
- Do not weaken a refusal to make a demo pass.

Report suspected vulnerabilities through the private process in
[SECURITY.md](../SECURITY.md).
