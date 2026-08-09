# Regression contract

| Explanation | Evidence to compare |
| --- | --- |
| Input or split drift | Case IDs, dataset digest, selection rule |
| Runner drift | Image, dependency, tool, timeout, locale |
| Model variance | Provider, model, sampling settings, repeated trials |
| Context loss | Input length, truncation, retrieval, prompt assembly |
| Tool failure | Arguments, response codes, retries, first failing step |
| Policy refusal | Policy version, declared capabilities, refusal event |
| Grader drift | Grader version, rubric, calibration cases |

Use `SUPPORTED`, `PLAUSIBLE`, or `WEAK` for evidence strength. These labels describe the supplied artifacts, not model confidence.
