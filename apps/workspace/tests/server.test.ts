import assert from "node:assert/strict";
import { once } from "node:events";
import { mkdtemp } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test, { type TestContext } from "node:test";

import { createWorkspaceServer } from "../src/server.js";

async function listen(server: Server): Promise<URL> {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Expected a TCP listener.");
  return new URL(`http://127.0.0.1:${address.port}/`);
}

function closeAfter(testContext: TestContext, ...servers: Server[]): void {
  testContext.after(async () => {
    await Promise.all(
      servers.map((server) => new Promise<void>((done) => server.close(() => done()))),
    );
  });
}

test("serves static assets and persists explicit review goals", async (testContext) => {
  const traceGate = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ mode: "offline_keyless", status: "ok" }));
  });
  const traceGateUrl = await listen(traceGate);
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-server-"));
  const workspace = createWorkspaceServer({
    dataPath: join(directory, "workspace.json"),
    traceGateUrl,
    webRoot: resolve("web"),
  });
  const workspaceUrl = await listen(workspace);
  closeAfter(testContext, workspace, traceGate);

  const page = await fetch(workspaceUrl);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /AWE Workspace/);
  assert.match(page.headers.get("content-security-policy") ?? "", /frame-ancestors 'none'/);

  const applicationScript = await fetch(new URL("/app.js", workspaceUrl));
  assert.equal(applicationScript.status, 200);
  assert.match(applicationScript.headers.get("content-type") ?? "", /javascript/);

  const font = await fetch(new URL("/fonts/AtkinsonHyperlegibleNext-Variable.ttf", workspaceUrl));
  assert.equal(font.status, 200);
  assert.match(font.headers.get("cache-control") ?? "", /immutable/);

  const created = await fetch(new URL("/api/goals", workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({ text: "  Inspect   this artifact  ", mode: "review" }),
  });
  assert.equal(created.status, 201);
  const createdBody = (await created.json()) as {
    goal: { goal_id: string; mode: string; state: string; text: string };
  };
  assert.equal(createdBody.goal.text, "Inspect this artifact");
  assert.equal(createdBody.goal.mode, "review");
  assert.equal(createdBody.goal.state, "ready_for_review");

  const capabilities = await fetch(new URL("/api/capabilities", workspaceUrl));
  const capabilityBody = (await capabilities.json()) as {
    capabilities: Array<{ id: string; state: string }>;
  };
  assert.equal(
    capabilityBody.capabilities.find((item) => item.id === "tracegate")?.state,
    "connected",
  );

  const removed = await fetch(
    new URL(`/api/goals/${encodeURIComponent(createdBody.goal.goal_id)}`, workspaceUrl),
    { method: "DELETE", headers: { Origin: workspaceUrl.origin } },
  );
  assert.equal(removed.status, 204);
  assert.deepEqual((await (await fetch(new URL("/api/goals", workspaceUrl))).json()).goals, []);
});

test("records and exports a real Discovery brief", async (testContext) => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-server-"));
  const workspace = createWorkspaceServer({
    dataPath: join(directory, "workspace.json"),
    traceGateUrl: new URL("http://127.0.0.1:1/"),
    webRoot: resolve("web"),
  });
  const workspaceUrl = await listen(workspace);
  closeAfter(testContext, workspace);

  const created = await fetch(new URL("/api/goals", workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({
      text: "Reduce flaky retries",
      mode: "discover",
      hypothesis: "Backoff reduces repeated failures",
      success_metric: "p95 retries decrease by 20%",
      baseline: "current retry policy",
    }),
  });
  const goal = ((await created.json()) as { goal: { goal_id: string; state: string } }).goal;
  assert.equal(goal.state, "discovery_planned");

  const evaluated = await fetch(
    new URL(`/api/goals/${goal.goal_id}/discovery`, workspaceUrl),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
      body: JSON.stringify({
        outcome: "better",
        summary: "18 of 20 frozen trials improved",
        evidence_ref: "artifacts/retry-eval.json",
      }),
    },
  );
  assert.equal(evaluated.status, 200);
  assert.equal(((await evaluated.json()) as { goal: { state: string } }).goal.state, "ready_for_gate");

  const exported = await fetch(new URL(`/api/goals/${goal.goal_id}/export`, workspaceUrl));
  assert.equal(exported.status, 200);
  const brief = (await exported.json()) as {
    schema_version: string;
    hypothesis: string;
    evaluation: { evidence_ref: string };
  };
  assert.equal(brief.schema_version, "awe.discovery-brief.v1");
  assert.equal(brief.hypothesis, "Backoff reduces repeated failures");
  assert.equal(brief.evaluation.evidence_ref, "artifacts/retry-eval.json");
});

test("rejects cross-origin mutations and invalid goal identifiers", async (testContext) => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-server-"));
  const workspace = createWorkspaceServer({
    dataPath: join(directory, "workspace.json"),
    traceGateUrl: new URL("http://127.0.0.1:1/"),
    webRoot: resolve("web"),
  });
  const workspaceUrl = await listen(workspace);
  closeAfter(testContext, workspace);

  const crossOrigin = await fetch(new URL("/api/goals", workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: "https://example.com" },
    body: JSON.stringify({ text: "Review evidence", mode: "review" }),
  });
  assert.equal(crossOrigin.status, 403);

  const invalidDelete = await fetch(new URL("/api/goals/not-a-goal", workspaceUrl), {
    method: "DELETE",
    headers: { Origin: workspaceUrl.origin },
  });
  assert.equal(invalidDelete.status, 400);
});

test("creates an explicit runtime handoff without an embedded executor", async (testContext) => {
  const directory = await mkdtemp(join(tmpdir(), "awe-workspace-server-"));
  const workspace = createWorkspaceServer({
    dataPath: join(directory, "workspace.json"),
    traceGateUrl: new URL("http://127.0.0.1:1/"),
    webRoot: resolve("web"),
  });
  const workspaceUrl = await listen(workspace);
  closeAfter(testContext, workspace);

  const health = await fetch(new URL("/api/health", workspaceUrl));
  assert.equal(((await health.json()) as { runtime: string }).runtime, "permissioned_handoff_v1");

  const goalResponse = await fetch(new URL("/api/goals", workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({ text: "Prepare a retry experiment", mode: "capture" }),
  });
  const goal = ((await goalResponse.json()) as { goal: { goal_id: string } }).goal;

  const proposed = await fetch(new URL(`/api/goals/${goal.goal_id}/runs`, workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({
      runner: "codex",
      requested_permissions: ["read_goal", "write_checkpoint"],
    }),
  });
  assert.equal(proposed.status, 201);
  const run = ((await proposed.json()) as { run: { run_id: string; state: string } }).run;
  assert.equal(run.state, "awaiting_approval");

  const unavailableHandoff = await fetch(new URL(`/api/runs/${run.run_id}/handoff`, workspaceUrl));
  assert.equal(unavailableHandoff.status, 400);

  const approved = await fetch(new URL(`/api/runs/${run.run_id}/approval`, workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({
      approved_by: "Ari",
      granted_permissions: ["read_goal", "write_checkpoint"],
    }),
  });
  assert.equal(approved.status, 200);
  assert.equal(((await approved.json()) as { run: { state: string } }).run.state, "handoff_ready");

  const handoff = await fetch(new URL(`/api/runs/${run.run_id}/handoff`, workspaceUrl));
  assert.equal(handoff.status, 200);
  const handoffBody = (await handoff.json()) as {
    schema_version: string;
    restrictions: string[];
    granted_permissions: string[];
  };
  assert.equal(handoffBody.schema_version, "awe.runtime-handoff.v1");
  assert.deepEqual(handoffBody.granted_permissions, ["read_goal", "write_checkpoint"]);
  assert.match(handoffBody.restrictions.join(" "), /No shell/);

  const checkpoint = await fetch(new URL(`/api/runs/${run.run_id}/checkpoint`, workspaceUrl), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({ summary: "Host drafted a plan", artifact_ref: "artifacts/plan.json" }),
  });
  assert.equal(checkpoint.status, 200);
  assert.equal(((await checkpoint.json()) as { run: { state: string } }).run.state, "checkpointed");

  const cancelled = await fetch(new URL(`/api/runs/${run.run_id}/cancel`, workspaceUrl), {
    method: "POST",
    headers: { Origin: workspaceUrl.origin },
  });
  assert.equal(cancelled.status, 200);
  assert.equal(((await cancelled.json()) as { run: { state: string } }).run.state, "cancelled");

  const escapedGrant = await fetch(new URL(`/api/runs/${run.run_id}/approval`, workspaceUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: workspaceUrl.origin },
    body: JSON.stringify({ approved_by: "Ari", granted_permissions: ["shell"] }),
  });
  assert.equal(escapedGrant.status, 400);
});
