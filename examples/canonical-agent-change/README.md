# Canonical synthetic agent-change fixture

This directory is one complete, offline Gate v2 example. It is synthetic test
data—not a benchmark, real model result, external-adopter pilot, or safety
claim. It contains no project source, credentials, prompts, or customer data.

The example proves a narrow engineering property: the versioned TraceGate
contracts can reproduce a linked `PASS` decision from checked-in held inputs.
It does not replay a model or tool call, authenticate the asserted reviewer and
judge labels, or generalize beyond these frozen cases.

## What is in the fixture

| Artifact | Purpose |
| --- | --- |
| `traces.jsonl` | Two consistent read-only traces used to compile the candidate |
| `baseline-*` / `candidate-*` | Paired frozen experiment manifests, v1 evaluation projections, and terminal-quality sidecars |
| `comparison*.json` | The controlled comparison, its exact-input verifier result, and policy |
| `evaluation-policy.json` | Stable Gate v1 evaluation policy replayed inside Gate v2 |
| `quality-policy.json` | Complete terminal-outcome and asserted calibration requirements |
| `gate-v2.json` | The content-addressed Gate v2 decision (`PASS`) |
| `explanation.json` | A deterministic receipt-dependency graph, limitations included |
| `fixture.json` | Fixture identity, expected statuses/hashes, and explicit limits |

## Replay it

From the repository root:

```bash
awe demo --out /tmp/awe-demo
awe doctor /tmp/awe-demo
```

That is the shortest complete tour from an installed package. To replay the
checked-in comparison and Gate v2 files individually:

```bash
python -m awe_tracegate.cli verify-comparison \
  --receipt examples/canonical-agent-change/comparison.json \
  --baseline examples/canonical-agent-change/baseline-manifest.json \
  --candidate examples/canonical-agent-change/candidate-manifest.json \
  --policy examples/canonical-agent-change/comparison-policy.json \
  --out /tmp/comparison-verification.json

python -m awe_tracegate.cli gate-v2 \
  --traces examples/canonical-agent-change/traces.jsonl \
  --baseline examples/canonical-agent-change/baseline-evaluation.json \
  --candidate examples/canonical-agent-change/candidate-evaluation.json \
  --evaluation-policy examples/canonical-agent-change/evaluation-policy.json \
  --comparison examples/canonical-agent-change/comparison.json \
  --baseline-experiment examples/canonical-agent-change/baseline-manifest.json \
  --candidate-experiment examples/canonical-agent-change/candidate-manifest.json \
  --comparison-policy examples/canonical-agent-change/comparison-policy.json \
  --baseline-quality examples/canonical-agent-change/baseline-quality.json \
  --candidate-quality examples/canonical-agent-change/candidate-quality.json \
  --quality-policy examples/canonical-agent-change/quality-policy.json \
  --out /tmp/gate-v2.json
```

Both commands operate only on local files. The checked-in fixture is regenerated
by `python scripts/generate_canonical_fixture.py --out examples/canonical-agent-change`
and byte-checked by `tests/test_canonical_agent_change_fixture.py`.
