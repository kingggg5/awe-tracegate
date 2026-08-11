# Related work and differentiation

AWE TraceGate combines established ideas; it does not claim to have invented
trace mining, workflow compilation, agent skills, replay, evaluation, or durable
execution. This page records the closest primary sources and makes the project
boundary explicit.

## Experiment and observability platforms

- [Braintrust experiments](https://www.braintrust.dev/docs/evaluate/run-evaluations)
  provide immutable evaluation snapshots, comparison, sharing, and CI/CD use.
- [LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation-concepts)
  connects datasets, experiments, evaluator scores, and execution traces across
  pre-deployment and production workflows.
- [Arize Phoenix](https://arize.com/docs/phoenix) is an open-source platform for
  tracing, evaluation, datasets, experiments, and troubleshooting.

These systems already cover much of the trace, experiment, comparison, and CI
workflow. TraceGate is not presented as a feature-complete replacement. Its
narrow contribution is a portable offline decision boundary: content-addressed
evidence linkage, consumer-owned replay expectations, fail-closed policy, and a
separate human decision. AWE's next research focus is the reliability of the
conclusion itself. Experimental comparison v1 adds paired-case uncertainty and
flakiness under exact declared controls. Gate v2 adds asserted judge-
calibration sidecars and bounded supplied environment/seed sensitivity; causal
attribution, grader trust, and extrapolation beyond supplied runs remain roadmap
items.

## Trace-to-procedure and skill work

- [Agent Workflow Optimization (AWO)](https://www.microsoft.com/en-us/research/publication/optimizing-agentic-workflows-using-meta-tools/)
  finds recurring tool-call sequences in traces and turns them into deterministic
  composite meta-tools.
- [TraceCompiler](https://arxiv.org/abs/2608.02680) mines noisy agent traces into
  mostly deterministic workflows, attaches evidence to admitted dependencies,
  and refuses an underdetermined irreversible workflow.
- [Trace2Skill](https://arxiv.org/abs/2603.25158) analyzes execution experience
  and consolidates trajectory-local lessons into transferable declarative skills.
- [SkillDisCo](https://arxiv.org/abs/2606.26669) distills reusable procedural
  control-flow subgraphs and compiles them into executable skills.
- [SkillOpt](https://github.com/microsoft/SkillOpt) optimizes natural-language
  skill documents through rollouts and held-out validation gates.
- [SkillGen](https://www.microsoft.com/en-us/research/publication/skillgen-verified-inference-time-agent-skill-synthesis/)
  uses successful and failed trajectories, then treats a generated skill as an
  intervention whose held-out effect must be measured against the baseline.

These projects make “trace to reusable skill/workflow” an active field rather
than a novelty claim available to TraceGate.

## Workflow optimization and routing

- [FlowCompile](https://arxiv.org/abs/2605.13647) explores model, reasoning, and
  workflow configurations before deployment to construct reusable
  accuracy-latency trade-offs.
- [Switchcraft](https://www.microsoft.com/en-us/research/publication/switchcraft-ai-model-router-for-agentic-tool-calling/)
  routes agentic tool-calling requests to lower-cost models subject to measured
  correctness.
- [EvoRoute](https://arxiv.org/abs/2601.02695) uses prior experience for dynamic
  model routing across cost, latency, and performance objectives.

TraceGate v0 does not route models or optimize configurations.

## Developer experience and loop catalogs

- [Loop Engineering](https://github.com/cobusgreyling/loop-engineering)
  provides a unified CLI front door, readiness doctor, machine-readable pattern
  catalog, copy-ready starters, and honest operating stories for recurring
  agent loops.

AWE adopts the useful onboarding principle, not the runtime scope. `awe demo`,
`awe doctor`, and the small decision-recipe catalog help a reviewer reach a
reproducible evidence result quickly. TraceGate still does not schedule loops,
run agents, create worktrees, execute shell commands, or auto-promote changes.

## Context and token optimization

- [Headroom](https://github.com/headroomlabs-ai/headroom) provides a local-first
  context-compression layer across tool output, JSON, logs, code, files, and
  agent integrations.
- [LLMLingua](https://github.com/microsoft/LLMLingua) studies learned prompt
  compression, including long-context and task-agnostic variants.

TraceGate is not another compressor, proxy, or context-memory product. A
discovery harness may evaluate these as interchangeable candidate strategies,
but any promotion must bind the exact strategy and frozen dataset, preserve
task and safety outcomes, and report latency, cost, and token usage. Claimed
token savings are experiment input, not verification evidence by themselves.

## Runtimes, replay, and evaluation

- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
  supports checkpoints, human-in-the-loop flows, memory, fault tolerance,
  replay, and state forks.
- [Temporal AI engineering](https://go.temporal.io/platform-hub/ai-engineering)
  applies durable execution, retries, persisted state, and audit history to
  long-running agents.
- [Langfuse evaluation](https://langfuse.com/docs/evaluation/core-concepts) and
  [Braintrust evaluation](https://www.braintrust.dev/docs/evaluate) connect
  traces, datasets, experiments, production scoring, and regression CI.
- [AgentDebugX](https://arxiv.org/abs/2607.18754) presents a detect, attribute,
  recover, and rerun loop for agent failures.
- [Causal Agent Replay](https://arxiv.org/abs/2606.08275) studies
  counterfactual intervention over stochastic agent trajectories.

TraceGate is not a durable runtime, observability backend, experiment tracker,
or causal debugger. External workspaces and harnesses may produce its evidence,
but their runtime responsibilities remain outside this verifier.

## Process and observability standards

- [Using Process Mining to Generate AI Agents from Software Engineering Process
  Records](https://arxiv.org/abs/2607.04948) explores deriving project-specific
  agent roles and specifications from repository event logs.
- [OpenTelemetry GenAI agent conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
  define developing conventions for agent, workflow, planning, and tool spans.
  In 2026 they moved to a dedicated repository and remain Development, so the
  importer pins revision `1d85c963ea51e9c7d24cc330ff67057f6e90e6c5` rather
  than treating `main` as a stable contract.

## What TraceGate is trying to contribute

The project’s distinction is deliberately operational rather than a claim of a
new algorithm:

1. a small offline and keyless review path;
2. immutable typed traces and workflow candidates;
3. explicit binding evidence for every admitted dependency;
4. refusal as a first-class, machine-readable result;
5. a canonical content-addressed receipt that can accompany later evaluation
   and human review;
6. no runtime, write action, or automatic promotion in the trusted boundary.

This combination should be judged by reproducibility, refusal correctness, and
usefulness in real reviews—not by the number of features or by claims that no
other project overlaps it.

The longer-term AWE thesis is equally narrow: **do not merely observe an agent;
determine whether the evidence justifies trusting the change.** That thesis is
an integration and reliability goal, not a claim that TraceGate invented replay,
evaluation, provenance, or causal analysis.
