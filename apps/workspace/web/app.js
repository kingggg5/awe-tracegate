const surfaces = Object.freeze({
  home: { element: document.querySelector("#homeSurface"), title: "Workspace", focus: "#homeTitle" },
  work: { element: document.querySelector("#workSurface"), title: "Work", focus: "#workTitle" },
  discovery: {
    element: document.querySelector("#discoverySurface"),
    title: "Discovery",
    focus: "#discoveryTitle",
  },
  tools: { element: document.querySelector("#toolsSurface"), title: "Tools", focus: "#toolsTitle" },
});

const elements = Object.freeze({
  allGoals: document.querySelector("#allGoals"),
  allGoalsEmpty: document.querySelector("#allGoalsEmpty"),
  baselineInput: document.querySelector("#baselineInput"),
  capabilityList: document.querySelector("#capabilityList"),
  connectionStatus: document.querySelector("#connectionStatus"),
  discoveryCandidates: document.querySelector("#discoveryCandidates"),
  discoveryCount: document.querySelector("#discoveryCount"),
  discoveryEmpty: document.querySelector("#discoveryEmpty"),
  discoveryFields: document.querySelector("#discoveryFields"),
  discoveryStatus: document.querySelector("#discoveryStatus"),
  form: document.querySelector("#goalForm"),
  formStatus: document.querySelector("#formStatus"),
  goalInput: document.querySelector("#goalInput"),
  hypothesisInput: document.querySelector("#hypothesisInput"),
  metricInput: document.querySelector("#metricInput"),
  recentEmpty: document.querySelector("#recentEmpty"),
  recentGoals: document.querySelector("#recentGoals"),
  refreshCapabilities: document.querySelector("#refreshCapabilities"),
  runtimeEmpty: document.querySelector("#runtimeEmpty"),
  runtimeForm: document.querySelector("#runtimeForm"),
  runtimeGoal: document.querySelector("#runtimeGoal"),
  runtimeRunner: document.querySelector("#runtimeRunner"),
  runtimeRuns: document.querySelector("#runtimeRuns"),
  runtimeStatus: document.querySelector("#runtimeStatus"),
  saveGoalButton: document.querySelector("#saveGoalButton"),
  surfaceTitle: document.querySelector("#surfaceTitle"),
  workStatus: document.querySelector("#workStatus"),
});

const state = {
  capabilities: [],
  goals: [],
  goalsLoaded: false,
  creatingRuntime: false,
  runs: [],
  runsLoaded: false,
  savingGoal: false,
  traceGateHref: null,
};

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const stateLabels = Object.freeze({
  draft: "Draft",
  discovery_planned: "Planned",
  discovery_evaluated: "Evaluated",
  ready_for_gate: "Ready for gate",
  ready_for_review: "Ready for review",
});

const runtimeStateLabels = Object.freeze({
  awaiting_approval: "Awaiting approval",
  handoff_ready: "Handoff ready",
  checkpointed: "Checkpointed",
  cancelled: "Cancelled",
});

const permissionLabels = Object.freeze({
  read_goal: "Read goal",
  read_evidence_references: "Read references",
  write_checkpoint: "Write checkpoints",
});

const runnerLabels = Object.freeze({
  codex: "Codex",
  claude_code: "Claude Code",
  external: "External runner",
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body
      ? { "Content-Type": "application/json", ...options.headers }
      : options.headers,
  });
  if (response.status === 204) return null;
  const body = await response
    .json()
    .catch(() => ({ error: "The local server returned an invalid response." }));
  if (!response.ok) throw new Error(body.error ?? `Request failed (${response.status}).`);
  return body;
}

function setSurface(name, { moveFocus = true } = {}) {
  const selected = surfaces[name];
  if (!selected) return;
  for (const [surfaceName, surface] of Object.entries(surfaces)) {
    surface.element.hidden = surfaceName !== name;
  }
  document.querySelectorAll(".primary-nav [data-surface]").forEach((control) => {
    if (control.dataset.surface === name) control.setAttribute("aria-current", "page");
    else control.removeAttribute("aria-current");
  });
  elements.surfaceTitle.textContent = selected.title;
  document.title = `${selected.title} · AWE Workspace`;
  if (name === "tools" && state.capabilities.length === 0) void loadCapabilities();
  if (moveFocus) document.querySelector(selected.focus)?.focus({ preventScroll: true });
  const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  window.scrollTo({ top: 0, behavior });
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatDate(timestamp) {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf()) ? "Unknown time" : dateFormatter.format(date);
}

function selectedMode() {
  return document.querySelector('input[name="mode"]:checked')?.value ?? "capture";
}

function setMode(mode) {
  const control = document.querySelector(`input[name="mode"][value="${mode}"]`);
  if (!control) return;
  control.checked = true;
  const discovering = mode === "discover";
  elements.discoveryFields.hidden = !discovering;
  elements.hypothesisInput.required = discovering;
  elements.metricInput.required = discovering;
  elements.goalInput.placeholder =
    mode === "review"
      ? "Name the evidence or evaluation to review..."
      : mode === "discover"
        ? "Name the workflow or behavior you want to improve..."
        : "Describe the work you want to keep...";
  elements.saveGoalButton.firstChild.textContent =
    mode === "discover" ? "Save discovery " : mode === "review" ? "Save review " : "Save goal ";
}

function stateBadge(goal) {
  const needsTraceGate =
    (goal.state === "ready_for_review" || goal.state === "ready_for_gate") &&
    !state.traceGateHref;
  const badge = element(
    "span",
    "goal-state",
    needsTraceGate ? "TraceGate required" : stateLabels[goal.state] ?? "Unknown",
  );
  badge.dataset.state = needsTraceGate ? "tracegate_required" : goal.state;
  return badge;
}

function traceGateLink(label = "Open TraceGate Review") {
  const link = element("a", "goal-action", label);
  link.href = state.traceGateHref;
  link.target = "_blank";
  link.rel = "noreferrer";
  return link;
}

function goalItem(goal, allowRemove) {
  const item = element("li", "work-item");
  const copy = element("div", "work-copy");
  copy.append(element("strong", "", goal.text));
  copy.append(
    element(
      "small",
      "",
      `${goal.mode.replace("discover", "discovery")} · ${goal.status_message} · ${formatDate(goal.updated_at)}`,
    ),
  );

  if (
    state.traceGateHref &&
    (goal.state === "ready_for_review" || goal.state === "ready_for_gate")
  ) {
    copy.append(traceGateLink());
  } else if (goal.mode === "discover") {
    const openDiscovery = element("button", "inline-action", "View discovery");
    openDiscovery.type = "button";
    openDiscovery.dataset.surface = "discovery";
    copy.append(openDiscovery);
  }

  const controls = element("div", "goal-controls");
  controls.append(stateBadge(goal));
  if (allowRemove) {
    const remove = element("button", "remove-goal", "Remove");
    remove.type = "button";
    remove.dataset.goalId = goal.goal_id;
    remove.setAttribute("aria-label", `Remove goal: ${goal.text}`);
    controls.append(remove);
  }
  item.append(copy, controls);
  return item;
}

function definition(term, value) {
  const group = element("div", "discovery-definition");
  group.append(element("dt", "", term), element("dd", "", value));
  return group;
}

function evaluationForm(goal) {
  const details = element("details", "evaluation-panel");
  if (!goal.discovery.evaluation) details.open = true;
  details.append(
    element(
      "summary",
      "",
      goal.discovery.evaluation ? "Update evaluation" : "Record evaluation",
    ),
  );
  const form = element("form", "evaluation-form");
  form.dataset.discoveryGoal = goal.goal_id;

  const outcomeLabel = element("label", "");
  outcomeLabel.append(element("span", "", "Outcome"));
  const select = element("select", "");
  select.name = "outcome";
  select.required = true;
  for (const [value, label] of [
    ["", "Select an outcome"],
    ["better", "Better"],
    ["same", "No material change"],
    ["worse", "Worse"],
    ["inconclusive", "Inconclusive"],
  ]) {
    const option = element("option", "", label);
    option.value = value;
    option.disabled = value === "";
    option.selected = goal.discovery.evaluation?.outcome
      ? value === goal.discovery.evaluation.outcome
      : value === "";
    select.append(option);
  }
  outcomeLabel.append(select);

  const referenceLabel = element("label", "");
  referenceLabel.append(element("span", "", "Evidence reference"));
  const reference = element("input", "");
  reference.name = "evidence_ref";
  reference.required = true;
  reference.maxLength = 1000;
  reference.placeholder = "path, receipt ID, or immutable URL";
  reference.value = goal.discovery.evaluation?.evidence_ref ?? "";
  referenceLabel.append(reference);

  const summaryLabel = element("label", "evaluation-summary");
  summaryLabel.append(element("span", "", "Evaluation summary"));
  const summary = element("textarea", "");
  summary.name = "summary";
  summary.required = true;
  summary.maxLength = 2000;
  summary.rows = 2;
  summary.placeholder = "Report trials, failures, and uncertainty.";
  summary.value = goal.discovery.evaluation?.summary ?? "";
  summaryLabel.append(summary);

  const submit = element(
    "button",
    "primary-action",
    goal.discovery.evaluation ? "Update outcome" : "Record outcome",
  );
  submit.type = "submit";
  form.append(outcomeLabel, referenceLabel, summaryLabel, submit);
  details.append(form);
  return details;
}

function discoveryItem(goal) {
  const item = element("li", "discovery-item");
  const heading = element("div", "discovery-item-heading");
  const title = element("div", "");
  title.append(
    element("strong", "", goal.text),
    element("small", "", `Updated ${formatDate(goal.updated_at)}`),
  );
  heading.append(title, stateBadge(goal));

  const definitions = element("dl", "discovery-definitions");
  definitions.append(
    definition("Hypothesis", goal.discovery.hypothesis),
    definition("Success metric", goal.discovery.success_metric),
  );
  if (goal.discovery.baseline) definitions.append(definition("Baseline", goal.discovery.baseline));
  if (goal.discovery.evaluation) {
    definitions.append(
      definition("Outcome", goal.discovery.evaluation.outcome.replace("same", "no material change")),
      definition("Evidence", goal.discovery.evaluation.evidence_ref),
      definition("Finding", goal.discovery.evaluation.summary),
    );
  }

  const actions = element("div", "discovery-actions");
  const exportLink = element("a", "secondary-action", "Export brief");
  exportLink.href = `/api/goals/${encodeURIComponent(goal.goal_id)}/export`;
  exportLink.download = `${goal.goal_id}-discovery-brief.json`;
  actions.append(exportLink);
  if (goal.state === "ready_for_gate" && state.traceGateHref) {
    actions.append(traceGateLink("Open gate"));
  }

  item.append(heading, definitions, actions, evaluationForm(goal));
  return item;
}

function renderGoals() {
  elements.recentGoals.replaceChildren(
    ...state.goals.slice(0, 4).map((goal) => goalItem(goal, false)),
  );
  elements.allGoals.replaceChildren(...state.goals.map((goal) => goalItem(goal, true)));
  elements.recentEmpty.hidden = state.goals.length > 0;
  elements.allGoalsEmpty.hidden = state.goals.length > 0;

  const discoveryGoals = state.goals.filter((goal) => goal.mode === "discover");
  elements.discoveryCandidates.replaceChildren(...discoveryGoals.map(discoveryItem));
  elements.discoveryEmpty.hidden = discoveryGoals.length > 0;
  elements.discoveryCount.textContent =
    discoveryGoals.length === 0
      ? "No candidates yet."
      : `${discoveryGoals.length} ${discoveryGoals.length === 1 ? "candidate" : "candidates"}.`;
  renderRuntimeGoalOptions();
  renderRuns();
}

function renderRuntimeGoalOptions() {
  const selectedGoalId = elements.runtimeGoal.value;
  elements.runtimeGoal.replaceChildren();
  if (state.goals.length === 0) {
    const empty = element("option", "", "Save a goal before preparing a handoff");
    empty.value = "";
    elements.runtimeGoal.append(empty);
  } else {
    for (const goal of state.goals) {
      const option = element("option", "", goal.text);
      option.value = goal.goal_id;
      option.selected = goal.goal_id === selectedGoalId;
      elements.runtimeGoal.append(option);
    }
  }
  const hasGoal = state.goals.length > 0;
  elements.runtimeGoal.disabled = !hasGoal || !state.runsLoaded;
  elements.runtimeRunner.disabled = !hasGoal || !state.runsLoaded;
  document.querySelector("#createRuntimeButton").disabled =
    !hasGoal || !state.runsLoaded || state.creatingRuntime;
}

function runtimeStateBadge(run) {
  const badge = element(
    "span",
    "runtime-state",
    runtimeStateLabels[run.state] ?? "Unknown",
  );
  badge.dataset.state = run.state;
  return badge;
}

function runtimeHandoffLink(run) {
  const link = element("a", "secondary-action", "Download handoff");
  link.href = `/api/runs/${encodeURIComponent(run.run_id)}/handoff`;
  link.download = `${run.run_id}-handoff.json`;
  return link;
}

function runtimeApprovalForm(run) {
  const details = element("details", "runtime-review-panel");
  details.append(element("summary", "", "Review and approve"));
  const form = element("form", "runtime-approval-form");
  form.dataset.runtimeApproval = run.run_id;
  const approver = element("label", "");
  approver.append(element("span", "", "Local reviewer"));
  const input = element("input", "");
  input.name = "approved_by";
  input.required = true;
  input.maxLength = 200;
  input.value = "local reviewer";
  approver.append(input);
  const disclosure = element(
    "p",
    "",
    "The reviewer name is a local assertion, not an authenticated identity. Approval grants exactly the permissions shown above.",
  );
  const submit = element("button", "primary-action", "Approve handoff");
  submit.type = "submit";
  form.append(approver, submit, disclosure);
  details.append(form);
  return details;
}

function runtimeCheckpointForm(run) {
  const details = element("details", "runtime-review-panel");
  details.append(element("summary", "", "Record checkpoint"));
  const form = element("form", "runtime-checkpoint-form");
  form.dataset.runtimeCheckpoint = run.run_id;

  const summary = element("label", "checkpoint-summary");
  summary.append(element("span", "", "Checkpoint summary"));
  const summaryInput = element("textarea", "");
  summaryInput.name = "summary";
  summaryInput.required = true;
  summaryInput.maxLength = 2000;
  summaryInput.rows = 2;
  summaryInput.placeholder = "What did the external runner report?";
  summary.append(summaryInput);

  const artifact = element("label", "checkpoint-artifact");
  artifact.append(element("span", "", "Artifact reference (optional)"));
  const artifactInput = element("input", "");
  artifactInput.name = "artifact_ref";
  artifactInput.maxLength = 1000;
  artifactInput.placeholder = "path, receipt ID, or immutable URL";
  artifact.append(artifactInput);

  const disclosure = element(
    "p",
    "",
    "A checkpoint is untrusted metadata. Send evidence to TraceGate separately before relying on it.",
  );
  const submit = element("button", "primary-action", "Save checkpoint");
  submit.type = "submit";
  form.append(summary, artifact, submit, disclosure);
  details.append(form);
  return details;
}

function runtimeItem(run) {
  const item = element("li", "runtime-item");
  const goal = state.goals.find((candidate) => candidate.goal_id === run.goal_id);
  const header = element("div", "runtime-item-header");
  const copy = element("div", "");
  copy.append(
    element("strong", "", goal?.text ?? "Removed goal"),
    element(
      "small",
      "",
      `${runnerLabels[run.runner] ?? "External runner"} · ${run.status_message} · ${formatDate(run.updated_at)}`,
    ),
  );
  header.append(copy, runtimeStateBadge(run));

  const permissions = element("div", "runtime-meta");
  for (const permission of run.requested_permissions) {
    permissions.append(element("span", "", permissionLabels[permission] ?? permission));
  }

  const actions = element("div", "runtime-actions");
  if (run.state === "handoff_ready" || run.state === "checkpointed") {
    actions.append(runtimeHandoffLink(run));
  }
  if (run.state !== "cancelled") {
    const cancel = element("button", "cancel-runtime", "Cancel local handoff");
    cancel.type = "button";
    cancel.dataset.runtimeCancel = run.run_id;
    actions.append(cancel);
  }
  item.append(header, permissions, actions);
  if (run.state === "awaiting_approval") item.append(runtimeApprovalForm(run));
  if (
    (run.state === "handoff_ready" || run.state === "checkpointed") &&
    run.approval?.granted_permissions.includes("write_checkpoint")
  ) {
    item.append(runtimeCheckpointForm(run));
  }
  return item;
}

function renderRuns() {
  elements.runtimeRuns.replaceChildren(...state.runs.map(runtimeItem));
  elements.runtimeEmpty.hidden = state.runs.length > 0;
}

async function loadGoals() {
  try {
    const body = await api("/api/goals");
    state.goals = body.goals;
    renderGoals();
  } catch (error) {
    elements.formStatus.dataset.state = "error";
    elements.formStatus.textContent = `Could not load saved goals. ${error.message}`;
  } finally {
    state.goalsLoaded = true;
    elements.saveGoalButton.disabled = false;
  }
}

async function loadRuns() {
  try {
    const body = await api("/api/runs");
    state.runs = body.runs;
    renderRuns();
  } catch (error) {
    elements.runtimeStatus.dataset.state = "error";
    elements.runtimeStatus.textContent = `Could not load runtime handoffs. ${error.message}`;
  } finally {
    state.runsLoaded = true;
    renderRuntimeGoalOptions();
  }
}

function capabilityRow(capability) {
  const row = element("div", "capability-row");
  const initials = capability.name
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2);
  const mark = element("span", "capability-mark", initials);
  mark.setAttribute("aria-hidden", "true");
  const copy = element("div", "capability-copy");
  copy.append(element("strong", "", capability.name), element("small", "", capability.description));
  let status;
  if (capability.id === "tracegate" && capability.state === "connected" && capability.href) {
    status = element("a", "capability-state", "Open review");
    status.href = capability.href;
    status.target = "_blank";
    status.rel = "noreferrer";
  } else {
    status = element("span", "capability-state", capability.state.replaceAll("_", " "));
  }
  status.dataset.state = capability.state;
  row.append(mark, copy, status);
  return row;
}

async function loadCapabilities() {
  elements.capabilityList.setAttribute("aria-busy", "true");
  elements.refreshCapabilities.disabled = true;
  try {
    const body = await api("/api/capabilities");
    state.capabilities = body.capabilities;
    const traceGate = state.capabilities.find((capability) => capability.id === "tracegate");
    state.traceGateHref = traceGate?.state === "connected" ? traceGate.href : null;
    elements.connectionStatus.textContent =
      traceGate?.state === "connected" ? "TraceGate connected" : "TraceGate unavailable";
    elements.connectionStatus.dataset.state = traceGate?.state ?? "unavailable";
    elements.capabilityList.replaceChildren(...state.capabilities.map(capabilityRow));
    renderGoals();
  } catch (error) {
    state.traceGateHref = null;
    elements.connectionStatus.textContent = "Workspace offline";
    elements.connectionStatus.dataset.state = "unavailable";
    elements.capabilityList.replaceChildren(
      element("p", "empty-row", `Could not check capabilities. ${error.message}`),
    );
  } finally {
    elements.capabilityList.setAttribute("aria-busy", "false");
    elements.refreshCapabilities.disabled = false;
  }
}

async function saveGoal(event) {
  event.preventDefault();
  if (!state.goalsLoaded || state.savingGoal) return;
  const mode = selectedMode();
  const payload = { text: elements.goalInput.value, mode };
  if (mode === "discover") {
    payload.hypothesis = elements.hypothesisInput.value;
    payload.success_metric = elements.metricInput.value;
    payload.baseline = elements.baselineInput.value;
  }
  state.savingGoal = true;
  elements.saveGoalButton.disabled = true;
  elements.formStatus.dataset.state = "";
  elements.formStatus.textContent = "Saving...";
  try {
    const body = await api("/api/goals", { method: "POST", body: JSON.stringify(payload) });
    state.goals = [body.goal, ...state.goals];
    elements.form.reset();
    setMode("capture");
    elements.formStatus.dataset.state = "success";
    elements.formStatus.textContent = body.goal.status_message;
    renderGoals();
  } catch (error) {
    elements.formStatus.dataset.state = "error";
    elements.formStatus.textContent = error.message;
  } finally {
    state.savingGoal = false;
    elements.saveGoalButton.disabled = false;
  }
}

async function recordEvaluation(form) {
  const goalId = form.dataset.discoveryGoal;
  const submit = form.querySelector("button[type=submit]");
  const values = new FormData(form);
  submit.disabled = true;
  elements.discoveryStatus.dataset.state = "";
  elements.discoveryStatus.textContent = "Recording evaluation...";
  try {
    const body = await api(`/api/goals/${encodeURIComponent(goalId)}/discovery`, {
      method: "PATCH",
      body: JSON.stringify({
        outcome: values.get("outcome"),
        evidence_ref: values.get("evidence_ref"),
        summary: values.get("summary"),
      }),
    });
    state.goals = state.goals.map((goal) => (goal.goal_id === goalId ? body.goal : goal));
    renderGoals();
    elements.discoveryStatus.dataset.state = "success";
    elements.discoveryStatus.textContent = body.goal.status_message;
    document
      .querySelector(`[data-discovery-goal="${goalId}"]`)
      ?.closest("details")
      ?.querySelector("summary")
      ?.focus();
  } catch (error) {
    submit.disabled = false;
    elements.discoveryStatus.dataset.state = "error";
    elements.discoveryStatus.textContent = `Could not record the evaluation. ${error.message}`;
  }
}

async function removeGoal(button) {
  const goalIndex = state.goals.findIndex((item) => item.goal_id === button.dataset.goalId);
  const goal = state.goals[goalIndex];
  if (!goal || !window.confirm(`Remove "${goal.text}" from this device?`)) return;
  button.disabled = true;
  elements.workStatus.dataset.state = "";
  elements.workStatus.textContent = "Removing goal...";
  try {
    await api(`/api/goals/${encodeURIComponent(goal.goal_id)}`, { method: "DELETE" });
    state.goals = state.goals.filter((item) => item.goal_id !== goal.goal_id);
    state.runs = state.runs.filter((run) => run.goal_id !== goal.goal_id);
    renderGoals();
    elements.workStatus.textContent = "Goal removed from this device.";
    const nextButtons = elements.allGoals.querySelectorAll("[data-goal-id]");
    (nextButtons[Math.min(goalIndex, nextButtons.length - 1)] ?? document.querySelector("#workTitle"))?.focus();
  } catch (error) {
    button.disabled = false;
    elements.workStatus.dataset.state = "error";
    elements.workStatus.textContent = `Could not remove the goal. ${error.message}`;
  }
}

function requestedRuntimePermissions() {
  return Array.from(document.querySelectorAll('input[name="runtimePermission"]:checked')).map(
    (input) => input.value,
  );
}

function upsertRun(run) {
  state.runs = [run, ...state.runs.filter((candidate) => candidate.run_id !== run.run_id)];
  renderRuns();
}

async function createRuntimeRun(event) {
  event.preventDefault();
  if (state.creatingRuntime || !state.runsLoaded) return;
  const goalId = elements.runtimeGoal.value;
  const requestedPermissions = requestedRuntimePermissions();
  if (!goalId || requestedPermissions.length === 0) {
    elements.runtimeStatus.dataset.state = "error";
    elements.runtimeStatus.textContent = "Select a goal and at least one narrow permission.";
    document.querySelector('input[name="runtimePermission"]')?.focus();
    return;
  }
  state.creatingRuntime = true;
  renderRuntimeGoalOptions();
  elements.runtimeStatus.dataset.state = "";
  elements.runtimeStatus.textContent = "Preparing a local handoff...";
  try {
    const body = await api(`/api/goals/${encodeURIComponent(goalId)}/runs`, {
      method: "POST",
      body: JSON.stringify({
        runner: elements.runtimeRunner.value,
        requested_permissions: requestedPermissions,
      }),
    });
    upsertRun(body.run);
    elements.runtimeStatus.dataset.state = "success";
    elements.runtimeStatus.textContent = body.run.status_message;
    const approvalForm = document.querySelector(`[data-runtime-approval="${body.run.run_id}"]`);
    const approvalPanel = approvalForm?.closest("details");
    if (approvalPanel) approvalPanel.open = true;
    approvalForm?.querySelector('input[name="approved_by"]')?.focus();
  } catch (error) {
    elements.runtimeStatus.dataset.state = "error";
    elements.runtimeStatus.textContent = `Could not prepare the handoff. ${error.message}`;
  } finally {
    state.creatingRuntime = false;
    renderRuntimeGoalOptions();
  }
}

async function approveRuntimeRun(form) {
  const runId = form.dataset.runtimeApproval;
  const run = state.runs.find((candidate) => candidate.run_id === runId);
  const submit = form.querySelector("button[type=submit]");
  if (!run || !submit) return;
  const values = new FormData(form);
  submit.disabled = true;
  elements.runtimeStatus.dataset.state = "";
  elements.runtimeStatus.textContent = "Recording local approval...";
  try {
    const body = await api(`/api/runs/${encodeURIComponent(runId)}/approval`, {
      method: "POST",
      body: JSON.stringify({
        approved_by: values.get("approved_by"),
        granted_permissions: run.requested_permissions,
      }),
    });
    upsertRun(body.run);
    elements.runtimeStatus.dataset.state = "success";
    elements.runtimeStatus.textContent = body.run.status_message;
    document.querySelector(`[href="/api/runs/${body.run.run_id}/handoff"]`)?.focus();
  } catch (error) {
    submit.disabled = false;
    elements.runtimeStatus.dataset.state = "error";
    elements.runtimeStatus.textContent = `Could not approve the handoff. ${error.message}`;
  }
}

async function recordRuntimeCheckpoint(form) {
  const runId = form.dataset.runtimeCheckpoint;
  const submit = form.querySelector("button[type=submit]");
  if (!runId || !submit) return;
  const values = new FormData(form);
  submit.disabled = true;
  elements.runtimeStatus.dataset.state = "";
  elements.runtimeStatus.textContent = "Saving checkpoint...";
  try {
    const body = await api(`/api/runs/${encodeURIComponent(runId)}/checkpoint`, {
      method: "PATCH",
      body: JSON.stringify({
        summary: values.get("summary"),
        artifact_ref: values.get("artifact_ref"),
      }),
    });
    upsertRun(body.run);
    elements.runtimeStatus.dataset.state = "success";
    elements.runtimeStatus.textContent = body.run.status_message;
    document
      .querySelector(`[data-runtime-checkpoint="${body.run.run_id}"]`)
      ?.closest("details")
      ?.querySelector("summary")
      ?.focus();
  } catch (error) {
    submit.disabled = false;
    elements.runtimeStatus.dataset.state = "error";
    elements.runtimeStatus.textContent = `Could not save the checkpoint. ${error.message}`;
  }
}

async function cancelRuntimeRun(button) {
  const runId = button.dataset.runtimeCancel;
  const run = state.runs.find((candidate) => candidate.run_id === runId);
  if (!run) return;
  if (
    !window.confirm(
      "Cancel this local handoff? Workspace cannot stop any work already started in the external runner.",
    )
  ) {
    return;
  }
  button.disabled = true;
  elements.runtimeStatus.dataset.state = "";
  elements.runtimeStatus.textContent = "Cancelling local handoff...";
  try {
    const body = await api(`/api/runs/${encodeURIComponent(run.run_id)}/cancel`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    upsertRun(body.run);
    elements.runtimeStatus.dataset.state = "success";
    elements.runtimeStatus.textContent = body.run.status_message;
    document.querySelector("#runtimeTitle")?.focus();
  } catch (error) {
    button.disabled = false;
    elements.runtimeStatus.dataset.state = "error";
    elements.runtimeStatus.textContent = `Could not cancel the handoff. ${error.message}`;
  }
}

document.addEventListener("click", (event) => {
  const surfaceControl = event.target.closest("[data-surface]");
  if (surfaceControl) setSurface(surfaceControl.dataset.surface, { moveFocus: event.detail === 0 });

  const suggestion = event.target.closest("[data-suggestion]");
  if (suggestion) {
    setSurface("home", { moveFocus: false });
    setMode(suggestion.dataset.mode ?? "capture");
    elements.goalInput.value = suggestion.dataset.suggestion;
    elements.hypothesisInput.value = suggestion.dataset.hypothesis ?? "";
    elements.metricInput.value = suggestion.dataset.metric ?? "";
    elements.baselineInput.value = suggestion.dataset.baseline ?? "";
    elements.goalInput.focus();
  }

  if (event.target.closest("[data-new-discovery]")) {
    setSurface("home", { moveFocus: false });
    setMode("discover");
    elements.goalInput.focus();
  }

  const remove = event.target.closest("[data-goal-id]");
  if (remove) void removeGoal(remove);

  const cancel = event.target.closest("[data-runtime-cancel]");
  if (cancel) void cancelRuntimeRun(cancel);
});

document.addEventListener("submit", (event) => {
  const evaluation = event.target.closest(".evaluation-form");
  if (evaluation) {
    event.preventDefault();
    void recordEvaluation(evaluation);
    return;
  }
  const approval = event.target.closest(".runtime-approval-form");
  if (approval) {
    event.preventDefault();
    void approveRuntimeRun(approval);
    return;
  }
  const checkpoint = event.target.closest(".runtime-checkpoint-form");
  if (checkpoint) {
    event.preventDefault();
    void recordRuntimeCheckpoint(checkpoint);
  }
});

elements.form.addEventListener("submit", saveGoal);
elements.form.addEventListener("change", (event) => {
  if (event.target.matches('input[name="mode"]')) setMode(event.target.value);
});
elements.goalInput.addEventListener("keydown", (event) => {
  if (
    state.goalsLoaded &&
    !state.savingGoal &&
    (event.ctrlKey || event.metaKey) &&
    event.key === "Enter"
  ) {
    elements.form.requestSubmit();
  }
});
elements.refreshCapabilities.addEventListener("click", loadCapabilities);
elements.runtimeForm.addEventListener("submit", createRuntimeRun);

setMode("capture");
await Promise.all([loadGoals(), loadRuns(), loadCapabilities()]);
