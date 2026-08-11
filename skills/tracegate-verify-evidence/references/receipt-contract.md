# Receipt contract

| Stage | Acceptable state | Stop state |
| --- | --- | --- |
| Compile | `compiled` | `refused` |
| Exact-input replay | `valid` and `traces_verified=true` | `invalid` or traces not verified |
| Frozen evaluation | `pass` | missing, `review`, or `block` |
| Human decision | Explicit separate approval or rejection | Missing or inconsistent chain |

Preserve input and dataset digests, source revision, tool versions, source trace IDs, reasons, command exit codes, and every receipt hash. A pass means the supplied evidence satisfied the supplied policy; it is not a safety certification.
