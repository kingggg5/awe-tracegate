# Decision recipes

TraceGate recipes begin with a decision and the evidence already produced by a
harness. They are not autonomous loops and never execute model, browser, shell,
deployment, or project-code actions.

## Catalog and safe scaffold

```bash
awe recipes
awe recipes --show controlled_comparison
awe recipes --json > decision-recipes.json
awe init --recipe controlled_comparison --out awe-evidence
```

The five built-in recipe IDs are `ci_gate`, `controlled_comparison`,
`harness_import`, `promotion_review`, and `share_evidence`. The catalog is a
content-addressed `awe.decision-recipe-catalog.v1`; it is small enough to audit
and stable enough for a Skill or integration to consume without fuzzy routing.

`awe init` is intentionally not a data generator. It creates a new directory
containing only a recipe README, explicit policy defaults when relevant, and a
raw-file-digest manifest. It refuses an existing output directory and never
creates trial results, evidence, consent, signatures, receipts, or decisions.
Preview it with:

```bash
awe init --recipe promotion_review --out awe-evidence --dry-run --json
```

## One-minute contract tour

```bash
awe demo --out awe-demo
awe doctor awe-demo
awe doctor awe-demo --json > review-bundle-report.json
```

This generates a synthetic Gate v2 bundle and then reloads every decision input.
`READY` means the comparison, Gate v2 receipt, typed quality evidence, and graph
reproduce from the held files. It does not mean a real agent improved.

## Prompt, Skill, or strategy change

Use this when the harness ran the same frozen cases and seeds before and after
one declared agent or strategy change.

Required inputs:

- baseline and candidate `ExperimentManifest` files;
- the same dataset and split digests, harness, grader, and environment;
- exactly one declared treatment unless the policy explicitly permits a joint
  effect;
- every attempted trial, including timeouts, refusals, infrastructure failures,
  and missing results.

```bash
awe compare \
  --baseline baseline-manifest.json \
  --candidate candidate-manifest.json \
  --policy comparison-policy.json \
  --out comparison.json

awe verify-comparison \
  --receipt comparison.json \
  --baseline baseline-manifest.json \
  --candidate candidate-manifest.json \
  --policy comparison-policy.json \
  --out comparison-verification.json
```

Use the receipt only for the supplied frozen cases. It is not a generalization
estimate, causal proof, or model replay.

## Model-only change

Keep the agent subject digest fixed and declare `model` as the treatment. A
changed subject, strategy, dataset, environment, harness, or grader introduces
another factor and must fail closed or be reviewed as a declared joint effect.
Use the same `compare` and `verify-comparison` commands above.

## Pull-request evidence gate

Use Gate v1 when CI already has traces and stable baseline/candidate evaluation
bundles. It is the smaller branch-protection contract.

```bash
awe gate \
  --traces traces.jsonl \
  --baseline baseline-evaluation.json \
  --candidate candidate-evaluation.json \
  --policy evaluation-policy.json \
  --out gate.json
```

Exit `0` means `PASS`, exit `2` means typed `REVIEW` or `BLOCK`, and exit `1`
means malformed input or invocation. A Skill or chat message cannot override
that result.

## Rich promotion review

Use Gate v2 when the reviewer also requires full-manifest comparison replay and
typed terminal/judge evidence. Follow the canonical bundle filenames so
`awe doctor` can re-check the complete directory.

```bash
awe gate-v2 \
  --traces traces.jsonl \
  --baseline baseline-evaluation.json \
  --candidate candidate-evaluation.json \
  --evaluation-policy evaluation-policy.json \
  --comparison comparison.json \
  --baseline-experiment baseline-manifest.json \
  --candidate-experiment candidate-manifest.json \
  --comparison-policy comparison-policy.json \
  --baseline-quality baseline-quality.json \
  --candidate-quality candidate-quality.json \
  --quality-policy quality-policy.json \
  --out gate-v2.json

awe explain gate-v2.json --out explanation.json
awe doctor .
```

`doctor` verifies linkage and reproducibility. A separate human decision is
still required for promotion. The v0.3 doctor profile covers this package-free
layout. When Gate v2 binds a Skill BOM or evidence package, replay it through
`gate-v2` with the separately controlled repository, commit, freshness, and
provenance expectations instead of treating `doctor` as authorization.

## Import another evaluation harness

Normalize first; gate second. The importer never invents ground truth.

```bash
awe import-experiment \
  --format generic \
  --input harness-export.json \
  --out experiment-manifest.json \
  --evaluation-out evaluation-bundle.json
```

The pinned `otel-genai` format is also supported. Vendor-specific adapters stay
outside the trusted core and should produce the same strict manifest contract.

## Share evidence for review

Redact locally and require an explicit consent record before evidence leaves the
repository. Signing proves who controlled a trusted key and which repository
revision was bound; it does not prove model quality or safety.

```bash
awe redact \
  --input gate-v2.json \
  --policy redaction-policy.json \
  --consent consent.json \
  --scope evaluation \
  --evaluated-at 2026-08-11T00:00:00Z \
  --out gate-v2.redacted.json \
  --summary redaction-summary.json
```

Do not upload automatically. Review the disclosure and residual-risk summary,
then use `awe sign` only when the recipient has an explicit trusted-key policy.
