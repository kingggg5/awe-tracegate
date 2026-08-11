import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { GoalStore } from "../src/store.js";

test("persists explicit modes in the v3 atomic local store", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const path = join(directory, "workspace.json");
  const store = new GoalStore(path);

  const created = await store.create(
    { text: "Review the evidence", mode: "review" },
    new Date("2026-08-09T00:00:00Z"),
  );
  const reloaded = await new GoalStore(path).list();

  assert.equal(reloaded[0]?.goal_id, created.goal_id);
  assert.equal(reloaded[0]?.state, "ready_for_review");
  assert.equal(JSON.parse(await readFile(path, "utf8")).schema_version, "awe.workspace-store.v3");
});

test("migrates the v1 store on the next mutation", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const path = join(directory, "workspace.json");
  await writeFile(
    path,
    JSON.stringify({
      schema_version: "awe.workspace-store.v1",
      goals: [
        {
          schema_version: "awe.workspace.goal.v1",
          goal_id: "goal_00000000-0000-4000-8000-000000000001",
          text: "Review the evidence",
          intent: "tracegate_review",
          state: "ready_for_review",
          created_at: "2026-08-08T00:00:00.000Z",
          updated_at: "2026-08-08T00:00:00.000Z",
          status_message: "Legacy message",
        },
      ],
    }),
  );
  const store = new GoalStore(path);

  assert.equal((await store.list())[0]?.mode, "review");
  await store.create({ text: "Keep this thought", mode: "capture" });

  const database = JSON.parse(await readFile(path, "utf8")) as {
    schema_version: string;
    goals: Array<{ schema_version: string; status_message: string }>;
  };
  assert.equal(database.schema_version, "awe.workspace-store.v3");
  assert.ok(database.goals.every((goal) => goal.schema_version === "awe.workspace.goal.v2"));
  assert.match(database.goals[0]?.status_message ?? "", /human-gated runtime handoff/);
});

test("records a discovery evaluation without claiming autonomous promotion", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const store = new GoalStore(join(directory, "workspace.json"));
  const goal = await store.create({
    text: "Reduce flaky retries",
    mode: "discover",
    hypothesis: "Backoff reduces repeat failures",
    success_metric: "p95 retries decrease by 20%",
    baseline: "current policy",
  });

  const updated = await store.recordDiscoveryEvaluation(
    goal.goal_id,
    {
      outcome: "better",
      summary: "18 of 20 frozen trials improved",
      evidence_ref: "artifacts/retry-eval.json",
    },
    new Date("2026-08-09T01:00:00Z"),
  );

  assert.equal(updated?.state, "ready_for_gate");
  assert.equal(updated?.discovery?.evaluation?.recorded_at, "2026-08-09T01:00:00.000Z");
  assert.match(updated?.status_message ?? "", /Ready for TraceGate review/);
});

test("serializes concurrent goal writes without losing records", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const store = new GoalStore(join(directory, "workspace.json"));

  await Promise.all([
    store.create({ text: "First draft", mode: "capture" }),
    store.create({ text: "Second draft", mode: "capture" }),
  ]);

  assert.equal((await store.list()).length, 2);
});

test("removes only the requested goal", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const store = new GoalStore(join(directory, "workspace.json"));
  const first = await store.create({ text: "First draft", mode: "capture" });
  await store.create({ text: "Second draft", mode: "capture" });

  assert.equal(await store.remove(first.goal_id), true);
  assert.equal(await store.remove(first.goal_id), false);
  assert.deepEqual((await store.list()).map((goal) => goal.text), ["Second draft"]);
});

test("coordinates an approved runtime handoff without executing tools", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const store = new GoalStore(join(directory, "workspace.json"));
  const goal = await store.create({ text: "Prepare a retry experiment", mode: "capture" });
  const proposed = await store.createRuntimeRun(
    goal.goal_id,
    { runner: "codex", requested_permissions: ["read_goal", "write_checkpoint"] },
    new Date("2026-08-11T02:00:00Z"),
  );

  assert.equal(proposed?.state, "awaiting_approval");
  const approved = await store.approveRuntimeRun(
    proposed!.run_id,
    { approved_by: "Ari", granted_permissions: ["read_goal", "write_checkpoint"] },
    new Date("2026-08-11T02:01:00Z"),
  );
  assert.equal(approved?.state, "handoff_ready");
  assert.match(approved?.status_message ?? "", /No tool has been executed/);

  const checkpointed = await store.recordRuntimeCheckpoint(
    proposed!.run_id,
    { summary: "Agent drafted a plan", artifact_ref: "artifacts/plan.json" },
    new Date("2026-08-11T02:02:00Z"),
  );
  assert.equal(checkpointed?.state, "checkpointed");
  assert.equal(checkpointed?.checkpoints[0]?.artifact_ref, "artifacts/plan.json");

  await assert.rejects(
    store.approveRuntimeRun(proposed!.run_id, {
      approved_by: "Ari",
      granted_permissions: ["read_goal", "write_checkpoint"],
    }),
    /awaiting approval/,
  );
});

test("refuses approval escalation and checkpoint writes without a matching grant", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const store = new GoalStore(join(directory, "workspace.json"));
  const goal = await store.create({ text: "Review evidence", mode: "review" });
  const proposed = await store.createRuntimeRun(goal.goal_id, {
    runner: "external",
    requested_permissions: ["read_goal"],
  });

  await assert.rejects(
    store.approveRuntimeRun(proposed!.run_id, {
      approved_by: "Ari",
      granted_permissions: ["read_goal", "write_checkpoint"],
    }),
    /exactly match/,
  );

  const approved = await store.approveRuntimeRun(proposed!.run_id, {
    approved_by: "Ari",
    granted_permissions: ["read_goal"],
  });
  assert.equal(approved?.state, "handoff_ready");
  await assert.rejects(
    store.recordRuntimeCheckpoint(proposed!.run_id, { summary: "Unexpected output" }),
    /checkpoint permission/,
  );
});

test("rejects a locally tampered runtime approval grant", async () => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-"));
  const path = join(directory, "workspace.json");
  const store = new GoalStore(path);
  const goal = await store.create({ text: "Review a trace bundle", mode: "capture" });
  const proposed = await store.createRuntimeRun(goal.goal_id, {
    runner: "external",
    requested_permissions: ["read_goal"],
  });
  await store.approveRuntimeRun(proposed!.run_id, {
    approved_by: "Ari",
    granted_permissions: ["read_goal"],
  });

  const database = JSON.parse(await readFile(path, "utf8")) as {
    runs: Array<{ approval: { granted_permissions: string[] } }>;
  };
  database.runs[0]!.approval.granted_permissions = ["write_checkpoint"];
  await writeFile(path, JSON.stringify(database));

  await assert.rejects(() => new GoalStore(path).listRuns(), /supported schema version/);
});
