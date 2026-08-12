import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  parseApproveRuntimeRunInput,
  parseCreateGoalInput,
  parseCreateRuntimeRunInput,
  parseDiscoveryEvaluationInput,
  parseRuntimeCheckpointInput,
  toDiscoveryBriefExport,
  toRuntimeHandoff,
  type Capability,
} from "./contracts.js";
import { GoalCapacityError, GoalStore, RuntimeCapacityError } from "./store.js";

const MAX_BODY_BYTES = 64 * 1024;
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
const SECURITY_HEADERS = Object.freeze({
  "Cache-Control": "no-store",
  "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
});

interface WorkspaceServerOptions {
  readonly dataPath: string;
  readonly traceGateUrl: URL;
  readonly webRoot: string;
}

function validateLoopbackUrl(rawUrl: string): URL {
  const url = new URL(rawUrl);
  if (url.protocol !== "http:" || !LOOPBACK_HOSTS.has(url.hostname)) {
    throw new Error("AWE_TRACEGATE_URL must be an http URL on a loopback host.");
  }
  return url;
}

function isLoopbackHostHeader(value: string | undefined): boolean {
  if (!value) return false;
  try {
    return LOOPBACK_HOSTS.has(new URL(`http://${value}`).hostname);
  } catch {
    return false;
  }
}

function writeJson(response: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    ...SECURITY_HEADERS,
    "Content-Length": Buffer.byteLength(payload),
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(payload);
}

function writeError(response: ServerResponse, status: number, message: string): void {
  writeJson(response, status, { error: message });
}

async function readJsonBody(request: IncomingMessage): Promise<unknown> {
  const contentType = request.headers["content-type"] ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    throw new TypeError("Content-Type must be application/json.");
  }

  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.byteLength;
    if (size > MAX_BODY_BYTES) {
      throw new RangeError("Request body exceeds the 64 KB limit.");
    }
    chunks.push(buffer);
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new SyntaxError("Request body is not valid JSON.");
  }
}

async function traceGateCapability(traceGateUrl: URL): Promise<Capability> {
  try {
    const healthUrl = new URL("/healthz", traceGateUrl);
    const response = await fetch(healthUrl, {
      redirect: "error",
      signal: AbortSignal.timeout(2_000),
    });
    const body = (await response.json()) as { mode?: unknown; status?: unknown };
    if (!response.ok || body.status !== "ok" || body.mode !== "offline_keyless") {
      throw new Error("unexpected TraceGate health response");
    }
    return {
      id: "tracegate",
      name: "AWE TraceGate",
      description: "Deterministic compile, replay, evaluation, and decision receipts.",
      state: "connected",
      href: traceGateUrl.toString(),
    };
  } catch {
    return {
      id: "tracegate",
      name: "AWE TraceGate",
      description: "Start TraceGate locally to review typed evidence.",
      state: "unavailable",
      href: traceGateUrl.toString(),
    };
  }
}

async function capabilities(traceGateUrl: URL): Promise<readonly Capability[]> {
  const traceGate = await traceGateCapability(traceGateUrl);
  return [
    traceGate,
    {
      id: "local_evidence",
      name: "Local evidence",
      description:
        traceGate.state === "connected"
          ? "Open JSONL traces and frozen evaluation artifacts in TraceGate."
          : "Start TraceGate before opening local evidence files.",
      state: traceGate.state === "connected" ? "available" : "unavailable",
    },
    {
      id: "agent_runtime",
      name: "Agent runtime handoff",
      description:
        "Create a local, human-approved handoff with bounded permissions and optional trace consent. Workspace does not execute tools.",
      state: "available",
    },
  ];
}

function sameOriginMutation(request: IncomingMessage): boolean {
  const fetchSite = request.headers["sec-fetch-site"];
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") return false;
  const origin = request.headers.origin;
  if (!origin) return true;
  try {
    return new URL(origin).host === request.headers.host;
  } catch {
    return false;
  }
}

function parseGoalIdSegment(value: string): string {
  let goalId: string;
  try {
    goalId = decodeURIComponent(value);
  } catch {
    throw new TypeError("Goal identifier is invalid.");
  }
  if (!/^goal_[0-9a-f-]{36}$/i.test(goalId)) {
    throw new TypeError("Goal identifier is invalid.");
  }
  return goalId;
}

function parseGoalSubresource(pathname: string, suffix: string): string | undefined {
  const prefix = "/api/goals/";
  if (!pathname.startsWith(prefix) || !pathname.endsWith(suffix)) return undefined;
  const encodedId = pathname.slice(prefix.length, -suffix.length);
  if (!encodedId || encodedId.includes("/")) return undefined;
  return parseGoalIdSegment(encodedId);
}

function parseRunIdSegment(value: string): string {
  let runId: string;
  try {
    runId = decodeURIComponent(value);
  } catch {
    throw new TypeError("Runtime run identifier is invalid.");
  }
  if (!/^run_[0-9a-f-]{36}$/i.test(runId)) {
    throw new TypeError("Runtime run identifier is invalid.");
  }
  return runId;
}

function parseRunSubresource(pathname: string, suffix: string): string | undefined {
  const prefix = "/api/runs/";
  if (!pathname.startsWith(prefix) || !pathname.endsWith(suffix)) return undefined;
  const encodedId = pathname.slice(prefix.length, -suffix.length);
  if (!encodedId || encodedId.includes("/")) return undefined;
  return parseRunIdSegment(encodedId);
}

export function createWorkspaceServer(options: WorkspaceServerOptions) {
  const store = new GoalStore(options.dataPath);
  const staticAssets: ReadonlyMap<string, readonly [string, string]> = new Map([
    ["/", ["index.html", "text/html; charset=utf-8"]],
    ["/app.js", ["app.js", "text/javascript; charset=utf-8"]],
    ["/styles.css", ["styles.css", "text/css; charset=utf-8"]],
    ["/fonts/AtkinsonHyperlegibleNext-Variable.ttf", ["fonts/AtkinsonHyperlegibleNext-Variable.ttf", "font/ttf"]],
  ] as const);

  return createServer(async (request, response) => {
    try {
      if (!isLoopbackHostHeader(request.headers.host)) {
        writeError(response, 400, "Host header must identify a loopback address.");
        return;
      }

      const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
      if (request.method === "GET" && url.pathname === "/api/health") {
        writeJson(response, 200, {
          status: "ok",
          mode: "local_first",
          runtime: "permissioned_handoff_v2",
        });
        return;
      }
      if (request.method === "GET" && url.pathname === "/api/goals") {
        writeJson(response, 200, { goals: await store.list() });
        return;
      }
      if (request.method === "GET" && url.pathname === "/api/capabilities") {
        writeJson(response, 200, { capabilities: await capabilities(options.traceGateUrl) });
        return;
      }
      if (request.method === "GET" && url.pathname === "/api/runs") {
        writeJson(response, 200, { runs: await store.listRuns() });
        return;
      }
      if (request.method === "POST" && url.pathname === "/api/goals") {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const input = parseCreateGoalInput(await readJsonBody(request));
        writeJson(response, 201, { goal: await store.create(input) });
        return;
      }

      const discoveryGoalId = parseGoalSubresource(url.pathname, "/discovery");
      if (request.method === "PATCH" && discoveryGoalId) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const input = parseDiscoveryEvaluationInput(await readJsonBody(request));
        const goal = await store.recordDiscoveryEvaluation(discoveryGoalId, input);
        if (!goal) {
          writeError(response, 404, "Goal not found.");
          return;
        }
        writeJson(response, 200, { goal });
        return;
      }

      const runtimeGoalId = parseGoalSubresource(url.pathname, "/runs");
      if (request.method === "POST" && runtimeGoalId) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const run = await store.createRuntimeRun(
          runtimeGoalId,
          parseCreateRuntimeRunInput(await readJsonBody(request)),
        );
        if (!run) {
          writeError(response, 404, "Goal not found.");
          return;
        }
        writeJson(response, 201, { run });
        return;
      }

      const approvalRunId = parseRunSubresource(url.pathname, "/approval");
      if (request.method === "POST" && approvalRunId) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const run = await store.approveRuntimeRun(
          approvalRunId,
          parseApproveRuntimeRunInput(await readJsonBody(request)),
        );
        if (!run) {
          writeError(response, 404, "Runtime run not found.");
          return;
        }
        writeJson(response, 200, { run });
        return;
      }

      const checkpointRunId = parseRunSubresource(url.pathname, "/checkpoint");
      if (request.method === "PATCH" && checkpointRunId) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const run = await store.recordRuntimeCheckpoint(
          checkpointRunId,
          parseRuntimeCheckpointInput(await readJsonBody(request)),
        );
        if (!run) {
          writeError(response, 404, "Runtime run not found.");
          return;
        }
        writeJson(response, 200, { run });
        return;
      }

      const revokeConsentRunId = parseRunSubresource(url.pathname, "/consent/revoke");
      if (request.method === "POST" && revokeConsentRunId) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const run = await store.revokeRuntimeTraceConsent(revokeConsentRunId);
        if (!run) {
          writeError(response, 404, "Runtime run not found.");
          return;
        }
        writeJson(response, 200, { run });
        return;
      }

      const cancelRunId = parseRunSubresource(url.pathname, "/cancel");
      if (request.method === "POST" && cancelRunId) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const run = await store.cancelRuntimeRun(cancelRunId);
        if (!run) {
          writeError(response, 404, "Runtime run not found.");
          return;
        }
        writeJson(response, 200, { run });
        return;
      }

      const handoffRunId = parseRunSubresource(url.pathname, "/handoff");
      if (request.method === "GET" && handoffRunId) {
        const run = await store.findRun(handoffRunId);
        if (!run) {
          writeError(response, 404, "Runtime run not found.");
          return;
        }
        const goal = await store.find(run.goal_id);
        if (!goal) {
          writeError(response, 404, "Goal not found.");
          return;
        }
        writeJson(response, 200, toRuntimeHandoff(goal, run));
        return;
      }

      const exportGoalId = parseGoalSubresource(url.pathname, "/export");
      if (request.method === "GET" && exportGoalId) {
        const goal = await store.find(exportGoalId);
        if (!goal) {
          writeError(response, 404, "Goal not found.");
          return;
        }
        writeJson(response, 200, toDiscoveryBriefExport(goal));
        return;
      }

      if (request.method === "DELETE" && url.pathname.startsWith("/api/goals/")) {
        if (!sameOriginMutation(request)) {
          writeError(response, 403, "Origin does not match this workspace.");
          return;
        }
        const encodedId = url.pathname.slice("/api/goals/".length);
        if (!encodedId || encodedId.includes("/")) {
          throw new TypeError("Goal identifier is invalid.");
        }
        const goalId = parseGoalIdSegment(encodedId);
        if (!(await store.remove(goalId))) {
          writeError(response, 404, "Goal not found.");
          return;
        }
        response.writeHead(204, SECURITY_HEADERS);
        response.end();
        return;
      }

      const asset = staticAssets.get(url.pathname);
      if (request.method === "GET" && asset) {
        const [fileName, contentType] = asset;
        const body = await readFile(resolve(options.webRoot, fileName));
        response.writeHead(200, {
          ...SECURITY_HEADERS,
          "Cache-Control": url.pathname.startsWith("/fonts/")
            ? "public, max-age=31536000, immutable"
            : "no-cache",
          "Content-Length": body.byteLength,
          "Content-Type": contentType,
        });
        response.end(body);
        return;
      }

      writeError(response, 404, "Resource not found.");
    } catch (error) {
      if (error instanceof GoalCapacityError || error instanceof RuntimeCapacityError) {
        writeError(response, 409, error.message);
      } else if (error instanceof RangeError) {
        writeError(response, 413, error.message);
      } else if (error instanceof SyntaxError || error instanceof TypeError) {
        writeError(response, 400, error.message);
      } else {
        console.error(error);
        writeError(response, 500, "Workspace request failed.");
      }
    }
  });
}

const modulePath = fileURLToPath(import.meta.url);
if (process.argv[1] && resolve(process.argv[1]) === resolve(modulePath)) {
  const host = process.env.AWE_WORKSPACE_HOST ?? "127.0.0.1";
  if (!LOOPBACK_HOSTS.has(host)) {
    throw new Error("AWE_WORKSPACE_HOST must be 127.0.0.1, localhost, or ::1.");
  }
  const port = Number.parseInt(process.env.AWE_WORKSPACE_PORT ?? "8787", 10);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error("AWE_WORKSPACE_PORT must be between 1 and 65535.");
  }

  const server = createWorkspaceServer({
    dataPath: resolve(process.env.AWE_WORKSPACE_DATA_DIR ?? ".data", "workspace.json"),
    traceGateUrl: validateLoopbackUrl(process.env.AWE_TRACEGATE_URL ?? "http://127.0.0.1:8765/"),
    webRoot: resolve(process.env.AWE_WORKSPACE_WEB_ROOT ?? "web"),
  });
  server.listen(port, host, () => {
    console.log(`AWE Workspace is ready at http://${host}:${port}`);
  });
}
