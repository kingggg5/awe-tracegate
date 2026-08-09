# Discovery evidence flow

Run from a trusted checkout after the external harness has produced the inputs:

```bash
awe compile --traces evidence/traces.jsonl --out compilation.json
awe verify --receipt compilation.json --traces evidence/traces.jsonl --out verification.json
awe evaluate --baseline evidence/baseline.json --candidate evidence/candidate.json --policy evidence/policy.json --out evaluation.json
```

Required interpretations:

- Compilation status is `compiled` or `refused`.
- Verification status is `valid` or `invalid`.
- Evaluation status is `pass`, `review`, or `block`.
- CLI exit `0` means the requested gate passed; `2` is a valid negative/review state; `1` is malformed input or an execution error.

Do not continue to promotion unless compilation is `compiled`, exact replay is `valid` with `traces_verified=true`, evaluation is `pass`, and a human explicitly decides.
