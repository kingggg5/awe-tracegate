# Security model

AWE TraceGate is a pre-alpha, offline reviewer. Its safest useful boundary
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
- requests to the optional HTTP API;
- JSONL and JSON files selected in the local Review Workspace.
- generic experiment exports and OTLP span attributes;
- signed bundles, embedded public keys, signer labels, and consent records.

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
- Experiment manifests bind repository, commit, frozen split, harness,
  strategy, model, environment, grader, trial, token, cost, and trace evidence.
- Ed25519 verification requires a separately supplied trusted key plus expected
  signer, repository, and commit; embedded trust material is insufficient.
- Governed export refuses revoked, expired, future, or out-of-scope consent.
- Evaluation receipts fail closed on dataset/case mismatch, seeded safety
  violations, and excessive success regression.
- Approval requires a compiled receipt, locally replayed exact traces, a valid
  verification receipt, and a passing evaluation for the identical candidate.
  The promotion receipt records every linked digest plus the actor and exact
  commit SHA.

## Important limitations

- SHA-256 integrity is not signer identity. Ed25519 proves possession of the
  trusted private key, not that a signer label is authorized. Operators must
  manage key-to-identity policy, rotation, revocation, and custody externally.
- Actor IDs in promotion receipts are assertions, not authenticated identities;
  use an operator-owned identity boundary before relying on them.
- A `compiled` decision does not prove semantic correctness, policy compliance,
  usefulness, or production safety.
- Repeated successful traces may contain correlated mistakes or incomplete
  coverage. Compilation does not create missing branches or counterexamples.
- Trace capture time and evidence freshness are not enforced in v0.2. Do not
  label evidence as current merely because its receipt replays; freshness needs
  immutable capture provenance and a pinned review time in a later contract.
- The local API is not an internet-facing deployment profile. It does not imply
  authentication, tenant isolation, rate limiting, or denial-of-service
  protection.
- Python process isolation is not a sandbox. AWE avoids executing trace content
  rather than claiming the host process contains hostile code.
- The OpenTelemetry GenAI conventions are still Development. TraceGate pins one
  reviewed revision and refuses legacy token aliases instead of silently
  guessing across schema generations.

## Sensitive data

Do not place credentials, access tokens, private source code, personal data,
customer payloads, or full production prompts in examples, issues, or public
receipts. Hashing a secret does not make publication safe: low-entropy values
may be guessed and metadata can still be sensitive.

Operators remain responsible for classifying, minimizing, redacting, retaining,
and deleting their trace data before AWE reads it. The project does not claim an
automatic PII or secret-redaction guarantee.

The built-in redactor is deliberately conservative and deterministic. It
handles explicit sensitive keys plus common email and token patterns, but it
cannot understand every customer schema, encoded secret, free-form identifier,
or inference attack. A redaction summary is evidence that rules ran—not proof
that an export is safe.

Governed mode additionally proves that a specific policy and consent record
were evaluated for one scope and UTC time. Consent metadata can itself be
sensitive. Revocation blocks new exports but cannot recall files already copied
outside the operator's control. Keep immutable audit records and enforce
retention/deletion in the downstream dataset registry.

## Signing guidance

The optional signing dependency is separate from the keyless compiler install.
Do not pass PEM passwords as command-line arguments; use the supported
environment-variable indirection or an external signing system. Keep private
keys outside the repository and CI artifacts. A valid self-signed bundle must
not be trusted unless the verifier receives the expected public key through a
separate operator-controlled channel.

## API guidance

If you expose the optional API outside a developer machine, place it behind an
operator-owned control plane that supplies authentication, authorization,
request-size limits, timeouts, audit logging, TLS, and network policy. Never use
the health endpoint or a successful compile response as authorization for a
side effect.

The Review Workspace is a local review convenience, not a hardened public web
application. Selected files are parsed by the page and sent to its same-origin
API. Its 10 MB browser file limit is a usability guard, not a server security
boundary; operators must still review and redact evidence before loading it.
Do not bind the API to a public interface without the operator-owned controls
above.

The command bar uses a fixed local allowlist and dispatches only existing review
actions. It does not evaluate prompt text, call a model, run shell commands, or
load arbitrary plugins. The tools view is an inventory, not an OAuth or secret
storage surface.

## Dependency and release hygiene

- Pin released artifacts and review dependency changes.
- Run the test suite before release.
- Keep compiler decisions covered by golden and adversarial fixtures.
- Treat changes to schemas, canonicalization, effect classification, and refusal
  rules as security-sensitive.
- Do not weaken a refusal to make a demo pass.

Report suspected vulnerabilities through the private process in
[SECURITY.md](../SECURITY.md).
