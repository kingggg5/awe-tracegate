import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyGoal,
  parseApproveRuntimeRunInput,
  parseCreateGoalInput,
  parseCreateRuntimeRunInput,
  parseDiscoveryEvaluationInput,
  parseRuntimeCheckpointInput,
  toRuntimeHandoff,
} from "../src/contracts.js";

test("keeps the legacy evidence-review classifier backward compatible", () => {
  assert.deepEqual(classifyGoal("Review these traces and verify the evidence"), {
    mode: "review",
    intent: "tracegate_review",
    state: "ready_for_review",
    status_message: "Ready for a deterministic TraceGate evidence review.",
  });
  assert.equal(classifyGoal("Trace a memory leak in production").state, "draft");
});

test("parses explicit capture and review modes without guessing intent", () => {
  assert.deepEqual(
    parseCreateGoalInput({ text: "  Compare   two designs  ", mode: "capture" }),
    { text: "Compare two designs", mode: "capture" },
  );
  assert.deepEqual(parseCreateGoalInput({ text: "Inspect the artifact", mode: "review" }), {
    text: "Inspect the artifact",
    mode: "review",
  });
});

test("requires a falsifiable discovery brief", () => {
  assert.deepEqual(
    parseCreateGoalInput({
      text: "Reduce flaky retries",
      mode: "discover",
      hypothesis: "  Backoff reduces repeated failures  ",
      success_metric: "p95 retry count decreases by 20%",
      baseline: "current retry policy",
    }),
    {
      text: "Reduce flaky retries",
      mode: "discover",
      hypothesis: "Backoff reduces repeated failures",
      success_metric: "p95 retry count decreases by 20%",
      baseline: "current retry policy",
    },
  );
  assert.throws(
    () => parseCreateGoalInput({ text: "Explore", mode: "discover" }),
    /Hypothesis/,
  );
  assert.throws(
    () => parseCreateGoalInput({ text: "Explore", mode: "automatic" }),
    /capture, review, or discover/,
  );
});

test("normalizes evaluation outcomes and rejects ambiguous values", () => {
  assert.deepEqual(
    parseDiscoveryEvaluationInput({
      outcome: "better",
      summary: "  Passed 18 of 20 frozen trials  ",
      evidence_ref: "artifacts/eval-2026-08-09.json",
    }),
    {
      outcome: "better",
      summary: "Passed 18 of 20 frozen trials",
      evidence_ref: "artifacts/eval-2026-08-09.json",
    },
  );
  assert.throws(
    () => parseDiscoveryEvaluationInput({ outcome: "probably", summary: "x", evidence_ref: "y" }),
    /Outcome/,
  );
});

test("validates required goal text", () => {
  assert.throws(() => parseCreateGoalInput({ text: "  ", mode: "capture" }), /goal text/i);
  assert.throws(
    () => parseCreateGoalInput({ text: "x".repeat(4_001), mode: "capture" }),
    /4,000/,
  );
});

test("requires a narrow, explicit runtime permission request", () => {
  assert.deepEqual(
    parseCreateRuntimeRunInput({
      runner: "codex",
      requested_permissions: ["write_checkpoint", "read_goal"],
    }),
    {
      runner: "codex",
      requested_permissions: ["read_goal", "write_checkpoint"],
    },
  );
  assert.throws(
    () => parseCreateRuntimeRunInput({ runner: "codex", requested_permissions: ["shell"] }),
    /unsupported permission/,
  );
  assert.throws(
    () => parseCreateRuntimeRunInput({ runner: "automatic", requested_permissions: ["read_goal"] }),
    /Runner/,
  );
  assert.throws(
    () => parseApproveRuntimeRunInput({ approved_by: "Ari", granted_permissions: [] }),
    /one to three/,
  );
  assert.deepEqual(
    parseApproveRuntimeRunInput({
      approved_by: "Ari",
      granted_permissions: ["read_goal"],
      trace_consent_scopes: ["evaluate_migration", "capture_trace"],
    }),
    {
      approved_by: "Ari",
      granted_permissions: ["read_goal"],
      trace_consent_scopes: ["capture_trace", "evaluate_migration"],
    },
  );
  assert.throws(
    () =>
      parseApproveRuntimeRunInput({
        approved_by: "Ari",
        granted_permissions: ["read_goal"],
        trace_consent_scopes: ["capture_trace", "capture_trace"],
      }),
    /duplicates/,
  );
  assert.throws(
    () =>
      parseApproveRuntimeRunInput({
        approved_by: "local reviewer",
        granted_permissions: ["read_goal"],
      }),
    /Reviewer ID/,
  );
  assert.deepEqual(
    parseRuntimeCheckpointInput({
      summary: "  External host produced a draft plan.  ",
      artifact_ref: "artifacts/plan.json",
    }),
    { summary: "External host produced a draft plan.", artifact_ref: "artifacts/plan.json" },
  );
});

test("runtime handoff requires an approved bounded run", () => {
  const goal = {
    schema_version: "awe.workspace.goal.v2" as const,
    goal_id: "goal_00000000-0000-4000-8000-000000000001",
    text: "Review a retry strategy",
    mode: "capture" as const,
    intent: "unconfigured_runtime" as const,
    state: "draft" as const,
    created_at: "2026-08-11T00:00:00.000Z",
    updated_at: "2026-08-11T00:00:00.000Z",
    status_message: "Draft",
  };
  const run = {
    schema_version: "awe.runtime-run.v1" as const,
    run_id: "run_00000000-0000-4000-8000-000000000001",
    goal_id: goal.goal_id,
    runner: "codex" as const,
    requested_permissions: ["read_goal"] as const,
    state: "handoff_ready" as const,
    approval: {
      approved_by: "Ari",
      granted_permissions: ["read_goal"] as const,
      approved_at: "2026-08-11T00:01:00.000Z",
    },
    checkpoints: [],
    created_at: "2026-08-11T00:00:00.000Z",
    updated_at: "2026-08-11T00:01:00.000Z",
    status_message: "Ready",
  };
  const handoff = toRuntimeHandoff(goal, run);
  assert.equal(handoff.schema_version, "awe.runtime-handoff.v2");
  assert.equal(handoff.state, "handoff_ready");
  assert.deepEqual(handoff.granted_permissions, ["read_goal"]);
  assert.match(handoff.restrictions.join(" "), /No shell/);
  const { approval: _approval, ...unapprovedRun } = run;
  assert.throws(
    () => toRuntimeHandoff(goal, { ...unapprovedRun, state: "awaiting_approval" }),
    /approved/,
  );
});
