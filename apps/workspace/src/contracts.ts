export const WORKSPACE_SCHEMA_VERSION = "awe.workspace.goal.v2" as const;
export const WORKSPACE_STORE_SCHEMA_VERSION = "awe.workspace-store.v3" as const;
export const DISCOVERY_BRIEF_SCHEMA_VERSION = "awe.discovery-brief.v1" as const;
export const RUNTIME_RUN_SCHEMA_VERSION = "awe.runtime-run.v1" as const;
export const RUNTIME_HANDOFF_SCHEMA_VERSION = "awe.runtime-handoff.v1" as const;

export type GoalMode = "capture" | "review" | "discover";
export type GoalIntent =
  | "tracegate_review"
  | "discovery_candidate"
  | "unconfigured_runtime";
export type GoalState =
  | "ready_for_review"
  | "draft"
  | "discovery_planned"
  | "discovery_evaluated"
  | "ready_for_gate";
export type DiscoveryOutcome = "better" | "same" | "worse" | "inconclusive";
export type RuntimeRunner = "codex" | "claude_code" | "external";
export type RuntimePermission =
  | "read_goal"
  | "read_evidence_references"
  | "write_checkpoint";
export type RuntimeRunState =
  | "awaiting_approval"
  | "handoff_ready"
  | "checkpointed"
  | "cancelled";

export interface DiscoveryEvaluation {
  readonly outcome: DiscoveryOutcome;
  readonly summary: string;
  readonly evidence_ref: string;
  readonly recorded_at: string;
}

export interface DiscoveryBrief {
  readonly hypothesis: string;
  readonly success_metric: string;
  readonly baseline?: string;
  readonly evaluation?: DiscoveryEvaluation;
}

export interface Goal {
  readonly schema_version: typeof WORKSPACE_SCHEMA_VERSION;
  readonly goal_id: string;
  readonly text: string;
  readonly mode: GoalMode;
  readonly intent: GoalIntent;
  readonly state: GoalState;
  readonly discovery?: DiscoveryBrief;
  readonly created_at: string;
  readonly updated_at: string;
  readonly status_message: string;
}

export interface RuntimeApproval {
  readonly approved_by: string;
  readonly granted_permissions: readonly RuntimePermission[];
  readonly approved_at: string;
}

export interface RuntimeCheckpoint {
  readonly summary: string;
  readonly artifact_ref?: string;
  readonly recorded_at: string;
}

export interface RuntimeRun {
  readonly schema_version: typeof RUNTIME_RUN_SCHEMA_VERSION;
  readonly run_id: string;
  readonly goal_id: string;
  readonly runner: RuntimeRunner;
  readonly requested_permissions: readonly RuntimePermission[];
  readonly state: RuntimeRunState;
  readonly approval?: RuntimeApproval;
  readonly checkpoints: readonly RuntimeCheckpoint[];
  readonly created_at: string;
  readonly updated_at: string;
  readonly status_message: string;
}

export interface WorkspaceDatabase {
  readonly schema_version: typeof WORKSPACE_STORE_SCHEMA_VERSION;
  readonly goals: readonly Goal[];
  readonly runs: readonly RuntimeRun[];
}

export interface DiscoveryBriefExport {
  readonly schema_version: typeof DISCOVERY_BRIEF_SCHEMA_VERSION;
  readonly goal_id: string;
  readonly goal: string;
  readonly hypothesis: string;
  readonly success_metric: string;
  readonly baseline?: string;
  readonly evaluation?: DiscoveryEvaluation;
  readonly workspace_state: GoalState;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface Capability {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly state: "connected" | "available" | "not_configured" | "unavailable";
  readonly href?: string;
}

export interface CreateGoalInput {
  readonly text: string;
  readonly mode: GoalMode;
  readonly hypothesis?: string;
  readonly success_metric?: string;
  readonly baseline?: string;
}

export interface RecordDiscoveryEvaluationInput {
  readonly outcome: DiscoveryOutcome;
  readonly summary: string;
  readonly evidence_ref: string;
}

export interface CreateRuntimeRunInput {
  readonly runner: RuntimeRunner;
  readonly requested_permissions: readonly RuntimePermission[];
}

export interface ApproveRuntimeRunInput {
  readonly approved_by: string;
  readonly granted_permissions: readonly RuntimePermission[];
}

export interface RecordRuntimeCheckpointInput {
  readonly summary: string;
  readonly artifact_ref?: string;
}

export interface RuntimeHandoff {
  readonly schema_version: typeof RUNTIME_HANDOFF_SCHEMA_VERSION;
  readonly run_id: string;
  readonly state: "handoff_ready" | "checkpointed";
  readonly runner: RuntimeRunner;
  readonly goal: Pick<Goal, "goal_id" | "text" | "mode" | "discovery">;
  readonly granted_permissions: readonly RuntimePermission[];
  readonly checkpoints: readonly RuntimeCheckpoint[];
  readonly restrictions: readonly string[];
  readonly created_at: string;
  readonly updated_at: string;
}

const MODE_VALUES = new Set<GoalMode>(["capture", "review", "discover"]);
const OUTCOME_VALUES = new Set<DiscoveryOutcome>([
  "better",
  "same",
  "worse",
  "inconclusive",
]);
const RUNTIME_RUNNER_VALUES = new Set<RuntimeRunner>(["codex", "claude_code", "external"]);
const RUNTIME_PERMISSION_VALUES = new Set<RuntimePermission>([
  "read_goal",
  "read_evidence_references",
  "write_checkpoint",
]);

function normalizeRequiredText(value: unknown, field: string, maximum: number): string {
  if (typeof value !== "string") throw new TypeError(`${field} must be a string.`);
  const normalized = value.trim().replace(/\s+/g, " ");
  if (!normalized) throw new TypeError(`Enter ${field.toLowerCase()} before saving.`);
  if (normalized.length > maximum) {
    throw new TypeError(`${field} must be ${maximum.toLocaleString("en-US")} characters or fewer.`);
  }
  return normalized;
}

function normalizeOptionalText(value: unknown, field: string, maximum: number): string | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  return normalizeRequiredText(value, field, maximum);
}

export function classifyGoal(text: string): Pick<Goal, "mode" | "intent" | "state" | "status_message"> {
  const normalized = text.trim().toLowerCase();
  const hasReviewVerb = /\b(review|validate|verify|compare)\b/.test(normalized);
  const hasEvidenceObject = /\b(evidence|evaluations?|receipts?|traces?)\b/.test(normalized);

  if (hasReviewVerb && hasEvidenceObject) {
    return {
      mode: "review",
      intent: "tracegate_review",
      state: "ready_for_review",
      status_message: "Ready for a deterministic TraceGate evidence review.",
    };
  }

  return {
    mode: "capture",
    intent: "unconfigured_runtime",
    state: "draft",
    status_message: "Saved as a draft. Prepare a human-gated runtime handoff when ready.",
  };
}

export function parseCreateGoalInput(value: unknown): CreateGoalInput {
  if (typeof value !== "object" || value === null || !("text" in value)) {
    throw new TypeError("Request body must contain a text field.");
  }

  const candidate = value as Record<string, unknown>;
  const text = normalizeRequiredText(candidate.text, "Goal text", 4_000);
  const suppliedMode = candidate.mode;

  // Keep the v1 API compatible while the UI always sends an explicit mode.
  if (suppliedMode === undefined) {
    return { text, mode: classifyGoal(text).mode };
  }
  if (typeof suppliedMode !== "string" || !MODE_VALUES.has(suppliedMode as GoalMode)) {
    throw new TypeError("Mode must be capture, review, or discover.");
  }

  const mode = suppliedMode as GoalMode;
  if (mode !== "discover") return { text, mode };

  const baseline = normalizeOptionalText(candidate.baseline, "Baseline", 500);
  return {
    text,
    mode,
    hypothesis: normalizeRequiredText(candidate.hypothesis, "Hypothesis", 1_000),
    success_metric: normalizeRequiredText(candidate.success_metric, "Success metric", 500),
    ...(baseline ? { baseline } : {}),
  };
}

export function parseDiscoveryEvaluationInput(value: unknown): RecordDiscoveryEvaluationInput {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("Evaluation body must be a JSON object.");
  }
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.outcome !== "string" ||
    !OUTCOME_VALUES.has(candidate.outcome as DiscoveryOutcome)
  ) {
    throw new TypeError("Outcome must be better, same, worse, or inconclusive.");
  }
  return {
    outcome: candidate.outcome as DiscoveryOutcome,
    summary: normalizeRequiredText(candidate.summary, "Evaluation summary", 2_000),
    evidence_ref: normalizeRequiredText(candidate.evidence_ref, "Evidence reference", 1_000),
  };
}

function parseRuntimePermissions(value: unknown, field: string): readonly RuntimePermission[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > RUNTIME_PERMISSION_VALUES.size) {
    throw new TypeError(`${field} must contain one to three supported permissions.`);
  }
  const permissions = value.map((item) => {
    if (typeof item !== "string" || !RUNTIME_PERMISSION_VALUES.has(item as RuntimePermission)) {
      throw new TypeError(`${field} contains an unsupported permission.`);
    }
    return item as RuntimePermission;
  });
  if (new Set(permissions).size !== permissions.length) {
    throw new TypeError(`${field} must not contain duplicate permissions.`);
  }
  return [...permissions].sort();
}

export function parseCreateRuntimeRunInput(value: unknown): CreateRuntimeRunInput {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("Runtime request body must be a JSON object.");
  }
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.runner !== "string" ||
    !RUNTIME_RUNNER_VALUES.has(candidate.runner as RuntimeRunner)
  ) {
    throw new TypeError("Runner must be codex, claude_code, or external.");
  }
  return {
    runner: candidate.runner as RuntimeRunner,
    requested_permissions: parseRuntimePermissions(
      candidate.requested_permissions,
      "Requested permissions",
    ),
  };
}

export function parseApproveRuntimeRunInput(value: unknown): ApproveRuntimeRunInput {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("Approval body must be a JSON object.");
  }
  const candidate = value as Record<string, unknown>;
  return {
    approved_by: normalizeRequiredText(candidate.approved_by, "Approver", 200),
    granted_permissions: parseRuntimePermissions(
      candidate.granted_permissions,
      "Granted permissions",
    ),
  };
}

export function parseRuntimeCheckpointInput(value: unknown): RecordRuntimeCheckpointInput {
  if (typeof value !== "object" || value === null) {
    throw new TypeError("Checkpoint body must be a JSON object.");
  }
  const candidate = value as Record<string, unknown>;
  const artifactRef = normalizeOptionalText(
    candidate.artifact_ref,
    "Artifact reference",
    1_000,
  );
  return {
    summary: normalizeRequiredText(candidate.summary, "Checkpoint summary", 2_000),
    ...(artifactRef ? { artifact_ref: artifactRef } : {}),
  };
}

export function toDiscoveryBriefExport(goal: Goal): DiscoveryBriefExport {
  if (goal.mode !== "discover" || !goal.discovery) {
    throw new TypeError("Only Discovery goals can be exported as discovery briefs.");
  }
  return {
    schema_version: DISCOVERY_BRIEF_SCHEMA_VERSION,
    goal_id: goal.goal_id,
    goal: goal.text,
    hypothesis: goal.discovery.hypothesis,
    success_metric: goal.discovery.success_metric,
    ...(goal.discovery.baseline ? { baseline: goal.discovery.baseline } : {}),
    ...(goal.discovery.evaluation ? { evaluation: goal.discovery.evaluation } : {}),
    workspace_state: goal.state,
    created_at: goal.created_at,
    updated_at: goal.updated_at,
  };
}

export function toRuntimeHandoff(goal: Goal, run: RuntimeRun): RuntimeHandoff {
  if (run.goal_id !== goal.goal_id) {
    throw new TypeError("Runtime run does not belong to this goal.");
  }
  if (!run.approval || (run.state !== "handoff_ready" && run.state !== "checkpointed")) {
    throw new TypeError("Runtime handoff requires an approved run.");
  }
  return {
    schema_version: RUNTIME_HANDOFF_SCHEMA_VERSION,
    run_id: run.run_id,
    state: run.state,
    runner: run.runner,
    goal: {
      goal_id: goal.goal_id,
      text: goal.text,
      mode: goal.mode,
      ...(goal.discovery ? { discovery: goal.discovery } : {}),
    },
    granted_permissions: run.approval.granted_permissions,
    checkpoints: run.checkpoints,
    restrictions: [
      "No shell, browser, network, credential, deployment, or promotion permission is granted.",
      "Do not treat agent output, checkpoints, or artifact references as TraceGate evidence.",
      "Use a separate human decision and TraceGate receipt before reuse or promotion.",
    ],
    created_at: run.created_at,
    updated_at: run.updated_at,
  };
}
