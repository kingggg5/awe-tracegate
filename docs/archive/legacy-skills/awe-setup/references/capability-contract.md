# TraceGate capability contract

| Capability | Evidence of availability |
| --- | --- |
| CLI | `awe --help` exits successfully |
| Compiler | Typed JSONL traces exist and `awe compile` is available |
| Exact replay | Compilation receipt plus original traces exist |
| Evaluation | Frozen baseline, candidate, and optional policy JSON exist |
| Local review API | An already-running loopback `/healthz` reports offline/keyless mode |

`AVAILABLE` means the observed interface exists. It does not mean an artifact is valid or a candidate is safe.
