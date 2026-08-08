# Related work and differentiation

AWE Agent Harness combines established ideas; it does not claim to have invented
trace mining, workflow compilation, agent skills, replay, evaluation, or durable
execution. This page records the closest primary sources and makes the project
boundary explicit.

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

These projects make “trace to reusable skill/workflow” an active field rather
than a novelty claim available to AWE.

## Workflow optimization and routing

- [FlowCompile](https://arxiv.org/abs/2605.13647) explores model, reasoning, and
  workflow configurations before deployment to construct reusable
  accuracy-latency trade-offs.
- [Switchcraft](https://www.microsoft.com/en-us/research/publication/switchcraft-ai-model-router-for-agentic-tool-calling/)
  routes agentic tool-calling requests to lower-cost models subject to measured
  correctness.
- [EvoRoute](https://arxiv.org/abs/2601.02695) uses prior experience for dynamic
  model routing across cost, latency, and performance objectives.

AWE v0 does not route models or optimize configurations.

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

AWE is not a durable runtime, observability backend, experiment tracker, or
causal debugger.

## Process and observability standards

- [Using Process Mining to Generate AI Agents from Software Engineering Process
  Records](https://arxiv.org/abs/2607.04948) explores deriving project-specific
  agent roles and specifications from repository event logs.
- [OpenTelemetry GenAI agent conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
  define developing conventions for agent, workflow, planning, and tool spans.
  Their current Development status means an importer must pin and version the
  schema it supports.

## What AWE is trying to contribute

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
