import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

import {
  WORKSPACE_SCHEMA_VERSION,
  WORKSPACE_STORE_SCHEMA_VERSION,
  RUNTIME_RUN_SCHEMA_VERSION,
  TRACE_CAPTURE_CONSENT_SCHEMA_VERSION,
  type ApproveRuntimeRunInput,
  classifyGoal,
  type CreateGoalInput,
  type CreateRuntimeRunInput,
  type DiscoveryBrief,
  type DiscoveryEvaluation,
  type Goal,
  type RecordRuntimeCheckpointInput,
  type RecordDiscoveryEvaluationInput,
  type RuntimeApproval,
  type RuntimeCheckpoint,
  type RuntimePermission,
  type RuntimeRun,
  type RuntimeRunState,
  type TraceCaptureConsent,
  type WorkspaceDatabase,
} from "./contracts.js";

const EMPTY_DATABASE: WorkspaceDatabase = {
  schema_version: WORKSPACE_STORE_SCHEMA_VERSION,
  goals: [],
  runs: [],
};

const MAX_GOALS = 500;
const MAX_RUNTIME_RUNS = 1_000;
const GOAL_MODES = new Set(["capture", "review", "discover"]);
const GOAL_INTENTS = new Set([
  "tracegate_review",
  "discovery_candidate",
  "unconfigured_runtime",
]);
const GOAL_STATES = new Set([
  "ready_for_review",
  "draft",
  "discovery_planned",
  "discovery_evaluated",
  "ready_for_gate",
]);
const DISCOVERY_OUTCOMES = new Set(["better", "same", "worse", "inconclusive"]);
const RUNTIME_RUNNERS = new Set(["codex", "claude_code", "external"]);
const RUNTIME_PERMISSIONS = new Set([
  "read_goal",
  "read_evidence_references",
  "write_checkpoint",
]);
const TRACE_CONSENT_SCOPES = new Set(["capture_trace", "evaluate_migration"]);
const RUNTIME_STATES = new Set<RuntimeRunState>([
  "awaiting_approval",
  "handoff_ready",
  "checkpointed",
  "cancelled",
]);

function samePermissions(
  left: readonly RuntimePermission[],
  right: readonly RuntimePermission[],
): boolean {
  return left.length === right.length && left.every((permission, index) => permission === right[index]);
}

export class GoalCapacityError extends Error {
  constructor() {
    super(`This local workspace stores at most ${MAX_GOALS} goals.`);
    this.name = "GoalCapacityError";
  }
}

export class RuntimeCapacityError extends Error {
  constructor() {
    super(`This local workspace stores at most ${MAX_RUNTIME_RUNS} runtime handoffs.`);
    this.name = "RuntimeCapacityError";
  }
}

function isDiscoveryEvaluation(value: unknown): value is DiscoveryEvaluation {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DiscoveryEvaluation>;
  return (
    typeof item.outcome === "string" &&
    DISCOVERY_OUTCOMES.has(item.outcome) &&
    typeof item.summary === "string" &&
    typeof item.evidence_ref === "string" &&
    typeof item.recorded_at === "string"
  );
}

function isDiscoveryBrief(value: unknown): value is DiscoveryBrief {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<DiscoveryBrief>;
  return (
    typeof item.hypothesis === "string" &&
    typeof item.success_metric === "string" &&
    (item.baseline === undefined || typeof item.baseline === "string") &&
    (item.evaluation === undefined || isDiscoveryEvaluation(item.evaluation))
  );
}

function isRuntimePermissions(value: unknown): value is RuntimeRun["requested_permissions"] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.length <= RUNTIME_PERMISSIONS.size &&
    value.every((permission) => typeof permission === "string" && RUNTIME_PERMISSIONS.has(permission)) &&
    new Set(value).size === value.length
  );
}

function isRuntimeApproval(value: unknown): value is RuntimeApproval {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<RuntimeApproval>;
  return (
    typeof item.approved_by === "string" &&
    isRuntimePermissions(item.granted_permissions) &&
    typeof item.approved_at === "string" &&
    (item.trace_consent === undefined || isTraceCaptureConsent(item.trace_consent))
  );
}

function isTraceCaptureConsent(value: unknown): value is TraceCaptureConsent {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TraceCaptureConsent>;
  const scopes = item.scopes;
  return (
    item.schema_version === TRACE_CAPTURE_CONSENT_SCHEMA_VERSION &&
    typeof item.consent_id === "string" &&
    typeof item.run_id === "string" &&
    typeof item.actor_id === "string" &&
    typeof item.runner === "string" &&
    RUNTIME_RUNNERS.has(item.runner) &&
    Array.isArray(scopes) &&
    scopes.length > 0 &&
    scopes.length <= TRACE_CONSENT_SCOPES.size &&
    scopes.every((scope) => typeof scope === "string" && TRACE_CONSENT_SCOPES.has(scope)) &&
    scopes.join(",") === [...scopes].sort().join(",") &&
    new Set(scopes).size === scopes.length &&
    (item.status === "active" || item.status === "revoked") &&
    typeof item.granted_at === "string" &&
    (item.expires_at === undefined || typeof item.expires_at === "string") &&
    (item.status === "active"
      ? item.revoked_at === undefined
      : typeof item.revoked_at === "string")
  );
}

function isRuntimeCheckpoint(value: unknown): value is RuntimeCheckpoint {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<RuntimeCheckpoint>;
  return (
    typeof item.summary === "string" &&
    (item.artifact_ref === undefined || typeof item.artifact_ref === "string") &&
    typeof item.recorded_at === "string"
  );
}

function isRuntimeRun(value: unknown): value is RuntimeRun {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<RuntimeRun>;
  const requestedPermissions = item.requested_permissions;
  const approval = item.approval;
  const consent = approval?.trace_consent;
  const hasApprovedState = item.state === "handoff_ready" || item.state === "checkpointed";
  return (
    item.schema_version === RUNTIME_RUN_SCHEMA_VERSION &&
    typeof item.run_id === "string" &&
    typeof item.goal_id === "string" &&
    typeof item.runner === "string" &&
    RUNTIME_RUNNERS.has(item.runner) &&
    isRuntimePermissions(requestedPermissions) &&
    typeof item.state === "string" &&
    RUNTIME_STATES.has(item.state as RuntimeRunState) &&
    (approval === undefined ||
      (isRuntimeApproval(approval) &&
        samePermissions(requestedPermissions, approval.granted_permissions) &&
        (consent === undefined ||
          (consent.run_id === item.run_id &&
            consent.runner === item.runner &&
            consent.actor_id === approval.approved_by &&
            consent.granted_at === approval.approved_at)))) &&
    Array.isArray(item.checkpoints) &&
    item.checkpoints.every(isRuntimeCheckpoint) &&
    (!hasApprovedState || approval !== undefined) &&
    (item.state !== "checkpointed" ||
      (item.checkpoints.length > 0 &&
        isRuntimeApproval(approval) &&
        approval.granted_permissions.includes("write_checkpoint"))) &&
    (item.state !== "awaiting_approval" || approval === undefined) &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string" &&
    typeof item.status_message === "string"
  );
}

function isGoal(value: unknown): value is Goal {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<Goal>;
  return (
    item.schema_version === WORKSPACE_SCHEMA_VERSION &&
    typeof item.goal_id === "string" &&
    typeof item.text === "string" &&
    typeof item.mode === "string" &&
    GOAL_MODES.has(item.mode) &&
    typeof item.intent === "string" &&
    GOAL_INTENTS.has(item.intent) &&
    typeof item.state === "string" &&
    GOAL_STATES.has(item.state) &&
    (item.discovery === undefined || isDiscoveryBrief(item.discovery)) &&
    (item.mode === "discover" ? isDiscoveryBrief(item.discovery) : item.discovery === undefined) &&
    typeof item.created_at === "string" &&
    typeof item.updated_at === "string" &&
    typeof item.status_message === "string"
  );
}

function migrateLegacyGoal(value: unknown): Goal | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const item = value as Record<string, unknown>;
  if (
    item.schema_version !== "awe.workspace.goal.v1" ||
    typeof item.goal_id !== "string" ||
    typeof item.text !== "string" ||
    (item.intent !== "tracegate_review" && item.intent !== "unconfigured_runtime") ||
    (item.state !== "ready_for_review" && item.state !== "draft") ||
    typeof item.created_at !== "string" ||
    typeof item.updated_at !== "string"
  ) {
    return undefined;
  }

  const classification =
    item.intent === "tracegate_review"
      ? {
          mode: "review" as const,
          intent: "tracegate_review" as const,
          state: "ready_for_review" as const,
          status_message: "Ready for a deterministic TraceGate evidence review.",
        }
      : classifyGoal(item.text);
  return {
    schema_version: WORKSPACE_SCHEMA_VERSION,
    goal_id: item.goal_id,
    text: item.text,
    ...classification,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

function parseDatabase(value: unknown): WorkspaceDatabase {
  if (typeof value !== "object" || value === null) {
    throw new Error("Workspace store is not a JSON object.");
  }
  const candidate = value as { schema_version?: unknown; goals?: unknown; runs?: unknown };
  if (!Array.isArray(candidate.goals)) {
    throw new Error("Workspace store goals must be an array.");
  }

  if (
    candidate.schema_version === WORKSPACE_STORE_SCHEMA_VERSION &&
    candidate.goals.every(isGoal) &&
    Array.isArray(candidate.runs) &&
    candidate.runs.every(isRuntimeRun)
  ) {
    return {
      schema_version: WORKSPACE_STORE_SCHEMA_VERSION,
      goals: [...candidate.goals],
      runs: [...candidate.runs],
    };
  }

  if (candidate.schema_version === "awe.workspace-store.v2" && candidate.goals.every(isGoal)) {
    return {
      schema_version: WORKSPACE_STORE_SCHEMA_VERSION,
      goals: [...candidate.goals],
      runs: [],
    };
  }

  if (candidate.schema_version === "awe.workspace-store.v1") {
    const goals = candidate.goals.map(migrateLegacyGoal);
    if (goals.every((goal): goal is Goal => goal !== undefined)) {
      return { schema_version: WORKSPACE_STORE_SCHEMA_VERSION, goals, runs: [] };
    }
  }

  throw new Error("Workspace store does not match a supported schema version.");
}

function createGoal(input: CreateGoalInput, now: Date): Goal {
  const timestamp = now.toISOString();
  const base = {
    schema_version: WORKSPACE_SCHEMA_VERSION,
    goal_id: `goal_${randomUUID()}`,
    text: input.text,
    created_at: timestamp,
    updated_at: timestamp,
  } as const;

  if (input.mode === "review") {
    return {
      ...base,
      mode: "review",
      intent: "tracegate_review",
      state: "ready_for_review",
      status_message: "Ready for a deterministic TraceGate evidence review.",
    };
  }
  if (input.mode === "discover") {
    if (!input.hypothesis || !input.success_metric) {
      throw new TypeError("Discovery goals require a hypothesis and success metric.");
    }
    return {
      ...base,
      mode: "discover",
      intent: "discovery_candidate",
      state: "discovery_planned",
      discovery: {
        hypothesis: input.hypothesis,
        success_metric: input.success_metric,
        ...(input.baseline ? { baseline: input.baseline } : {}),
      },
      status_message: "Discovery brief saved. Record a replayable evaluation before review.",
    };
  }
  return {
    ...base,
    mode: "capture",
    intent: "unconfigured_runtime",
    state: "draft",
    status_message: "Saved as a draft. Prepare a human-gated runtime handoff when ready.",
  };
}

function createRuntimeRun(
  goalId: string,
  input: CreateRuntimeRunInput,
  now: Date,
): RuntimeRun {
  const timestamp = now.toISOString();
  return {
    schema_version: RUNTIME_RUN_SCHEMA_VERSION,
    run_id: `run_${randomUUID()}`,
    goal_id: goalId,
    runner: input.runner,
    requested_permissions: input.requested_permissions,
    state: "awaiting_approval",
    checkpoints: [],
    created_at: timestamp,
    updated_at: timestamp,
    status_message: "Awaiting an explicit local approval before handoff.",
  };
}

export class GoalStore {
  readonly #path: string;
  #writeQueue: Promise<void> = Promise.resolve();

  constructor(path: string) {
    this.#path = path;
  }

  async list(): Promise<readonly Goal[]> {
    const database = await this.#read();
    return [...database.goals].sort((left, right) =>
      right.updated_at.localeCompare(left.updated_at),
    );
  }

  async find(goalId: string): Promise<Goal | undefined> {
    return (await this.#read()).goals.find((goal) => goal.goal_id === goalId);
  }

  async create(input: CreateGoalInput, now = new Date()): Promise<Goal> {
    const goal = createGoal(input, now);
    await this.#enqueue(async () => {
      const database = await this.#read();
      if (database.goals.length >= MAX_GOALS) throw new GoalCapacityError();
      await this.#write({ ...database, goals: [goal, ...database.goals] });
    });
    return goal;
  }

  async recordDiscoveryEvaluation(
    goalId: string,
    input: RecordDiscoveryEvaluationInput,
    now = new Date(),
  ): Promise<Goal | undefined> {
    let updated: Goal | undefined;
    await this.#enqueue(async () => {
      const database = await this.#read();
      const existing = database.goals.find((goal) => goal.goal_id === goalId);
      if (!existing) return;
      if (existing.mode !== "discover" || !existing.discovery) {
        throw new TypeError("Only Discovery goals accept evaluation outcomes.");
      }
      const timestamp = now.toISOString();
      const evaluatedGoal: Goal = {
        ...existing,
        state: input.outcome === "better" ? "ready_for_gate" : "discovery_evaluated",
        discovery: {
          ...existing.discovery,
          evaluation: { ...input, recorded_at: timestamp },
        },
        updated_at: timestamp,
        status_message:
          input.outcome === "better"
            ? "Candidate improved on the declared metric. Ready for TraceGate review."
            : "Evaluation recorded. The candidate is not marked ready for promotion.",
      };
      updated = evaluatedGoal;
      await this.#write({
        ...database,
        goals: database.goals.map((goal) =>
          goal.goal_id === goalId ? evaluatedGoal : goal,
        ),
      });
    });
    return updated;
  }

  async listRuns(goalId?: string): Promise<readonly RuntimeRun[]> {
    const runs = (await this.#read()).runs;
    return runs
      .filter((run) => goalId === undefined || run.goal_id === goalId)
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at));
  }

  async findRun(runId: string): Promise<RuntimeRun | undefined> {
    return (await this.#read()).runs.find((run) => run.run_id === runId);
  }

  async createRuntimeRun(
    goalId: string,
    input: CreateRuntimeRunInput,
    now = new Date(),
  ): Promise<RuntimeRun | undefined> {
    let created: RuntimeRun | undefined;
    await this.#enqueue(async () => {
      const database = await this.#read();
      if (!database.goals.some((goal) => goal.goal_id === goalId)) return;
      if (database.runs.length >= MAX_RUNTIME_RUNS) throw new RuntimeCapacityError();
      created = createRuntimeRun(goalId, input, now);
      await this.#write({ ...database, runs: [created, ...database.runs] });
    });
    return created;
  }

  async approveRuntimeRun(
    runId: string,
    approval: ApproveRuntimeRunInput,
    now = new Date(),
  ): Promise<RuntimeRun | undefined> {
    let updated: RuntimeRun | undefined;
    await this.#enqueue(async () => {
      const database = await this.#read();
      const existing = database.runs.find((run) => run.run_id === runId);
      if (!existing) return;
      if (existing.state !== "awaiting_approval") {
        throw new TypeError("Only a run awaiting approval can be handed off.");
      }
      if (!samePermissions(existing.requested_permissions, approval.granted_permissions)) {
        throw new TypeError("Granted permissions must exactly match the requested permissions.");
      }
      const timestamp = now.toISOString();
      const traceConsentScopes = approval.trace_consent_scopes ?? [];
      const traceConsent: TraceCaptureConsent | undefined =
        traceConsentScopes.length > 0
          ? {
              schema_version: TRACE_CAPTURE_CONSENT_SCHEMA_VERSION,
              consent_id: `consent_${randomUUID()}`,
              run_id: existing.run_id,
              actor_id: approval.approved_by,
              runner: existing.runner,
              scopes: traceConsentScopes,
              status: "active",
              granted_at: timestamp,
            }
          : undefined;
      updated = {
        ...existing,
        state: "handoff_ready",
        approval: {
          approved_by: approval.approved_by,
          granted_permissions: approval.granted_permissions,
          approved_at: timestamp,
          ...(traceConsent ? { trace_consent: traceConsent } : {}),
        },
        updated_at: timestamp,
        status_message: "Approved for external handoff. No tool has been executed by Workspace.",
      };
      await this.#write({
        ...database,
        runs: database.runs.map((run) => (run.run_id === runId ? updated! : run)),
      });
    });
    return updated;
  }

  async revokeRuntimeTraceConsent(
    runId: string,
    now = new Date(),
  ): Promise<RuntimeRun | undefined> {
    let updated: RuntimeRun | undefined;
    await this.#enqueue(async () => {
      const database = await this.#read();
      const existing = database.runs.find((run) => run.run_id === runId);
      if (!existing) return;
      const consent = existing.approval?.trace_consent;
      if (!consent) throw new TypeError("This handoff has no trace consent to revoke.");
      if (consent.status === "revoked") {
        updated = existing;
        return;
      }
      const timestamp = now.toISOString();
      updated = {
        ...existing,
        approval: {
          ...existing.approval!,
          trace_consent: { ...consent, status: "revoked", revoked_at: timestamp },
        },
        updated_at: timestamp,
        status_message: "Trace consent revoked. Previously exported data must be handled separately.",
      };
      await this.#write({
        ...database,
        runs: database.runs.map((run) => (run.run_id === runId ? updated! : run)),
      });
    });
    return updated;
  }

  async recordRuntimeCheckpoint(
    runId: string,
    input: RecordRuntimeCheckpointInput,
    now = new Date(),
  ): Promise<RuntimeRun | undefined> {
    let updated: RuntimeRun | undefined;
    await this.#enqueue(async () => {
      const database = await this.#read();
      const existing = database.runs.find((run) => run.run_id === runId);
      if (!existing) return;
      if (existing.state !== "handoff_ready" && existing.state !== "checkpointed") {
        throw new TypeError("Checkpoints require an approved runtime handoff.");
      }
      if (!existing.approval?.granted_permissions.includes("write_checkpoint")) {
        throw new TypeError("This runtime handoff was not granted checkpoint permission.");
      }
      const timestamp = now.toISOString();
      const checkpoint: RuntimeCheckpoint = { ...input, recorded_at: timestamp };
      updated = {
        ...existing,
        state: "checkpointed",
        checkpoints: [...existing.checkpoints, checkpoint],
        updated_at: timestamp,
        status_message: "Checkpoint recorded. Artifact references remain untrusted until TraceGate review.",
      };
      await this.#write({
        ...database,
        runs: database.runs.map((run) => (run.run_id === runId ? updated! : run)),
      });
    });
    return updated;
  }

  async cancelRuntimeRun(runId: string, now = new Date()): Promise<RuntimeRun | undefined> {
    let updated: RuntimeRun | undefined;
    await this.#enqueue(async () => {
      const database = await this.#read();
      const existing = database.runs.find((run) => run.run_id === runId);
      if (!existing) return;
      if (existing.state === "cancelled") {
        updated = existing;
        return;
      }
      const timestamp = now.toISOString();
      const activeConsent = existing.approval?.trace_consent;
      const approval =
        activeConsent?.status === "active"
          ? {
              ...existing.approval!,
              trace_consent: {
                ...activeConsent,
                status: "revoked" as const,
                revoked_at: timestamp,
              },
            }
          : existing.approval;
      updated = {
        ...existing,
        state: "cancelled",
        ...(approval ? { approval } : {}),
        updated_at: timestamp,
        status_message:
          "Runtime handoff cancelled and local trace consent revoked. External work and copies must be handled separately.",
      };
      await this.#write({
        ...database,
        runs: database.runs.map((run) => (run.run_id === runId ? updated! : run)),
      });
    });
    return updated;
  }

  async remove(goalId: string): Promise<boolean> {
    let removed = false;
    await this.#enqueue(async () => {
      const database = await this.#read();
      const goals = database.goals.filter((goal) => goal.goal_id !== goalId);
      removed = goals.length !== database.goals.length;
      if (removed) {
        await this.#write({
          ...database,
          goals,
          runs: database.runs.filter((run) => run.goal_id !== goalId),
        });
      }
    });
    return removed;
  }

  async #read(): Promise<WorkspaceDatabase> {
    try {
      return parseDatabase(JSON.parse(await readFile(this.#path, "utf8")));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return EMPTY_DATABASE;
      throw error;
    }
  }

  async #write(database: WorkspaceDatabase): Promise<void> {
    await mkdir(dirname(this.#path), { mode: 0o700, recursive: true });
    const temporaryPath = join(dirname(this.#path), `.workspace-${randomUUID()}.tmp`);
    await writeFile(temporaryPath, `${JSON.stringify(database, null, 2)}\n`, {
      encoding: "utf8",
      flag: "wx",
      flush: true,
      mode: 0o600,
    });
    await rename(temporaryPath, this.#path);
  }

  async #enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.#writeQueue.then(operation, operation);
    this.#writeQueue = next.catch(() => undefined);
    await next;
  }
}
