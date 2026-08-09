# TraceGate receipt contract

| Stage | Acceptable state | Stop state |
| --- | --- | --- |
| Compile | `compiled` | `refused` |
| Exact replay | `valid` and `traces_verified=true` | `invalid` or traces not verified |
| Frozen evaluation | `pass` | `review` or `block` |
| Human decision | Explicit separate `approved` or `rejected` receipt | Missing or inconsistent evidence chain |

Preserve `receipt_hash`, input or dataset digests, compiler/evaluator versions, source trace IDs, reasons, and command exit codes. A TraceGate pass is policy satisfaction for the supplied evidence, not universal safety.
