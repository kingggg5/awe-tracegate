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
- JSONL and JSON files selected in the local TraceGate Review UI;
- generic experiment exports and OTLP span attributes;
- Agent Skill folders, Skill BOMs, evidence envelopes, and evidence packages;
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
- The atomic gate cannot pass without a compiled candidate, exact source-trace
  replay, a passing frozen evaluation, and an identical candidate digest across
  the compilation and evaluation.
- Optional evidence packages bind the repository, exact commit, producer and
  environment digests, capture time, provenance level, and every supplied gate
  input. Signed or attested labels require a separate verification-artifact
  digest rather than a bare string assertion.
- Approval requires a compiled receipt, locally replayed exact traces, a valid
  verification receipt, and a passing evaluation for the identical candidate.
  The promotion receipt records every linked digest plus the actor and exact
  commit SHA.

## Important limitations

- SHA-256 integrity is not signer identity. Ed25519 proves possession of the
  trusted private key, not that a signer label is authorized. Operators must
  manage key-to-identity policy, rotation, revocation, and custody externally.
- Reviewer identifiers in promotion receipts are assertions, not authenticated
  identities. TraceGate Review labels this field accordingly; use an
  operator-owned identity boundary before relying on it.
- The human-decision form starts with no selection. This prevents accidental
  default approval in the UI, but it does not authenticate or authorize the
  reviewer.
- A `compiled` decision does not prove semantic correctness, policy compliance,
  usefulness, or production safety.
- Repeated successful traces may contain correlated mistakes or incomplete
  coverage. Compilation does not create missing branches or counterexamples.
- Freshness is enforced only when a valid evidence package, an explicit UTC
  evaluation time, and a maximum age are supplied to the gate. A receipt without
  those fields proves no freshness, even when exact replay succeeds.
- A `signature_verified` or `attested` provenance label plus a verification
  artifact digest does not establish trust by itself. The caller must verify the
  external signature or attestation against an operator-owned policy before
  constructing that envelope. TraceGate v0.3 therefore records those labels but
  refuses to use them as an enforceable minimum; only `asserted` is supported.
- The local API is not an internet-facing deployment profile. It does not imply
  authentication, tenant isolation, rate limiting, or denial-of-service
  protection.
- Python process isolation is not a sandbox. TraceGate avoids executing trace
  content rather than claiming the host process contains hostile code.
- The OpenTelemetry GenAI conventions are still Development. TraceGate pins one
  reviewed revision and refuses legacy token aliases instead of silently
  guessing across schema generations.

## Sensitive data

Do not place credentials, access tokens, private source code, personal data,
customer payloads, or full production prompts in examples, issues, or public
receipts. Hashing a secret does not make publication safe: low-entropy values
may be guessed and metadata can still be sensitive.

Operators remain responsible for classifying, minimizing, redacting, retaining,
and deleting their trace data before TraceGate reads it. The project does not
claim an automatic PII or secret-redaction guarantee.

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

TraceGate Review is a local review convenience, not a hardened public web
application or an agent runtime. Selected files are parsed by the page and sent
to its same-origin API. Its 10 MB browser file limit is a usability guard, not
a server security boundary; operators must still review and redact evidence
before loading it. Do not bind the API to a public interface without the
operator-owned controls above.

TraceGate Review exposes explicit buttons and forms for existing review actions.
It has no natural-language composer and does not evaluate prompt text, call a
model, run shell commands, or load arbitrary plugins. The tools view is an
inventory, not an OAuth or secret storage surface.

AWE Workspace owns the separate goal/command composer and is a different
application and process boundary. Connecting it to TraceGate does not give
Workspace permission to change gate policy, authenticate a reviewer, or turn
its own output into approval. Treat Workspace traces as untrusted evidence at
the same typed ingestion boundary as every other producer.

## Dependency and release hygiene

- Pin released artifacts and review dependency changes.
- Run the test suite before release.
- Keep compiler decisions covered by golden and adversarial fixtures.
- Treat changes to schemas, canonicalization, effect classification, and refusal
  rules as security-sensitive.
- Treat Skill, npm installer, Git marketplace, and Action changes as supply-chain
  sensitive. Installers must not use lifecycle scripts or overwrite unmanaged
  files.
- Do not weaken a refusal to make a demo pass.

Report suspected vulnerabilities through the private process in
[SECURITY.md](../SECURITY.md).
