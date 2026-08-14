const $ = (selector) => document.querySelector(selector);
const add = (parent, tag, value, className) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  parent.append(element);
  return element;
};
const jsonOptions = (value) => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});
const putOptions = (value) => ({
  method: "PUT",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});

let selected = null;
let projectData = null;
let activeTask = null;
let activePlan = null;
let creatingTask = false;
let mode = "agent";
let tab = "interaction";
let submittingAnswers = false;
let busy = false;
let activitySource = null;
let activityTaskId = null;
let activityEvents = [];
let activityPoller = null;
let activityPollPending = false;
const contextNotices = new Map();
const modal = $("#modal");

function currentProject() {
  return projectData?.project;
}
function taskKey() {
  return activeTask?.id || "system";
}
function notice(value) {
  if (!value) return;
  const key = taskKey();
  const entries = contextNotices.get(key) || [];
  entries.push({ id: crypto.randomUUID(), content: value });
  contextNotices.set(key, entries.slice(-5));
  if (selected) renderInteraction();
}
function setBackendState(online, message) {
  const element = $("#backend-status");
  element.className = `status-pill ${online ? "online" : "offline"}`;
  element.textContent = message;
}
async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    setBackendState(false, "Backend offline");
    throw new Error(`Unable to reach the Sagitta backend: ${error.message}`);
  }
  const raw = await response.text();
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_) {
    throw new Error(`Backend returned an unreadable HTTP ${response.status} response`);
  }
  if (!payload.ok) throw new Error(payload.error.message);
  setBackendState(true, "Backend online");
  return payload.data;
}

function openModal({ title, kicker = "", content }) {
  $("#modal-title").textContent = title;
  $("#modal-kicker").textContent = kicker;
  const body = $("#modal-body");
  body.replaceChildren();
  content(body);
  modal.showModal();
}
function closeModal() {
  modal.close();
}
function statusText(status) {
  return (
    {
      planning: "Reading the workspace and drafting the Plan Package",
      repairing_ir: "Repairing IR structure",
      reviewing_plan: "Running an independent pre-launch review",
      revising_plan: "Revising from review findings",
      needs_input: "Awaiting this decision round",
      ready: "Pre-launch review passed; Goal can be exported",
      planning_failed: "Planning failed",
      planning_review_failed: "Pre-launch review failed",
      invalid_ir: "IR could not be repaired",
    }[status] ||
    status ||
    "—"
  );
}
function renderTaskHeader() {
  const project = currentProject();
  if (!project) return;
  const title = activeTask?.title || (creatingTask ? "New task" : project.label);
  const context = activeTask
    ? `TASK · ${activePlan ? statusText(activePlan.status) : "draft"}`
    : creatingTask
      ? `NEW TASK · ${mode.toUpperCase()}`
      : `PROJECT · ${project.label}`;
  $("#project-kicker").textContent = context;
  $("#project-title").textContent = title;
  $("#workspace").textContent = project.workspace;
}
function setMode(next) {
  mode = next;
  document
    .querySelectorAll("[data-mode]")
    .forEach((button) =>
      button.setAttribute("aria-pressed", String(button.dataset.mode === mode)),
    );
  renderInteraction();
}
function setTab(next) {
  tab = next;
  document
    .querySelectorAll("[data-tab]")
    .forEach((button) =>
      button.setAttribute("aria-pressed", String(button.dataset.tab === tab)),
    );
  $("#interaction-tab").hidden = tab !== "interaction";
  $("#visualization-tab").hidden = tab !== "visualization";
  if (tab === "visualization") renderVisualization();
}

function renderProjects(projects) {
  const root = $("#projects");
  root.replaceChildren();
  $("#empty-projects").hidden = projects.length > 0;
  projects.forEach((project) => {
    const group = add(root, "div", "", `project-group${project.id === selected ? " active" : ""}`);
    const entry = add(group, "div", "", "project-entry");
    const button = add(entry, "button", project.label, "project");
    button.type = "button";
    button.title = project.workspace;
    button.onclick = async () => {
      closeActivityStream();
      selected = project.id;
      activeTask = null;
      activePlan = null;
      creatingTask = false;
      await loadProject();
    };
    if (project.id !== selected || projectData?.project?.id !== project.id)
      return;
    const newTask = add(entry, "button", "+", "new-task");
    newTask.type = "button";
    newTask.title = "New task";
    newTask.setAttribute("aria-label", "New task");
    newTask.onclick = openNewTask;
    const list = add(group, "div", "", "project-plan-list");
    const tasks = projectData.tasks || [];
    if (!tasks.length) {
      add(list, "small", "No tasks yet.", "project-plan-empty");
      return;
    }
    tasks.forEach((task) => {
      const row = add(list, "div", "", "project-plan-row");
      const taskButton = add(
        row,
        "button",
        task.title || task.id,
        "sidebar-plan" + (task.id === activeTask?.id ? " active" : ""),
      );
      taskButton.type = "button";
      taskButton.title = task.plan?.status ? statusText(task.plan.status) : "Task draft";
      taskButton.onclick = () => selectTask(task.id);
      const remove = add(row, "button", "×", "plan-delete");
      remove.type = "button";
      remove.setAttribute("aria-label", "Delete task");
      remove.title = "Delete this task, its conversation, Plan package, and local records";
      remove.onclick = () => confirmDeleteTask(task);
    });
  });
}
async function loadProjects() {
  const { projects } = await api("/api/projects");
  if (selected && !projects.some((item) => item.id === selected)) selected = null;
  if (!selected) selected = projects.find((item) => item.available)?.id ?? null;
  if (selected) await loadProject();
  else renderEmptyProject();
  renderProjects(projects);
}
function renderEmptyProject() {
  projectData = null;
  activeTask = null;
  activePlan = null;
  creatingTask = false;
  $("#project-kicker").textContent = "NO PROJECT SELECTED";
  $("#project-title").textContent = "Select a project";
  $("#workspace").textContent = "Choose a project directory from Finder using the + button.";
  $("#messages").replaceChildren();
  renderVisualization();
}
function message(root, role, content, extra = "", metadata = {}) {
  const card = add(root, "div", "", `message ${role} ${extra}`);
  const speaker = role === "user" ? "You" : metadata.route === "direct" ? "Planner" : "Sagitta";
  add(card, "div", speaker, "message-status");
  add(card, "div", content);
  return card;
}
function observesActivity(plan) {
  return ["planning", "repairing_ir", "reviewing_plan", "revising_plan", "needs_input"].includes(plan?.status);
}
function closeActivityStream() {
  if (activitySource) activitySource.close();
  if (activityPoller) clearInterval(activityPoller);
  activitySource = null;
  activityPoller = null;
  activityPollPending = false;
  activityTaskId = null;
}
function processActivityPacket(packet) {
  if (packet.type === "ACTIVITY_SNAPSHOT" && packet.activityType === "sagitta.executor_activity") {
    const activity = packet.content;
    if (activity?.id && !activityEvents.some((item) => item.id === activity.id)) {
      activityEvents.push(activity);
      return true;
    }
  }
  return false;
}
function parseActivityPackets(text) {
  return text
    .split("\n")
    .filter((line) => line.startsWith("data: "))
    .flatMap((line) => {
      try {
        return [JSON.parse(line.slice(6))];
      } catch (_) {
        return [];
      }
    });
}
async function pollActivity() {
  if (!selected || !activeTask || !activePlan || activityPollPending) return;
  activityPollPending = true;
  try {
    const response = await fetch(`/api/projects/${selected}/tasks/${activeTask.id}/activity?snapshot=1`);
    if (!response.ok) return;
    const changed = parseActivityPackets(await response.text()).some(processActivityPacket);
    await hydrateTask(activeTask.id);
    if (changed || !observesActivity(activePlan)) renderInteraction();
  } catch (_) {
    // The health indicator handles visible backend failures; polling retries.
  } finally {
    activityPollPending = false;
  }
}
function syncActivityStream() {
  if (!selected || !activeTask || !activePlan || !observesActivity(activePlan)) {
    closeActivityStream();
    return;
  }
  if (activityTaskId === activeTask.id && activitySource) return;
  closeActivityStream();
  activityTaskId = activeTask.id;
  activityEvents = [];
  if (!window.EventSource) {
    pollActivity();
    activityPoller = setInterval(pollActivity, 700);
    return;
  }
  activitySource = new EventSource(`/api/projects/${selected}/tasks/${activeTask.id}/activity?watch=1`);
  activitySource.onmessage = (event) => {
    let packet;
    try {
      packet = JSON.parse(event.data);
    } catch (_) {
      return;
    }
    if (processActivityPacket(packet)) return renderInteraction();
    if (packet.type === "RUN_FINISHED") {
      closeActivityStream();
      loadProject().catch((error) => notice(error.message));
    }
  };
  activitySource.onerror = () => {
    if (!activitySource) return;
    setTimeout(() => {
      if (activitySource && activityTaskId === activeTask?.id) {
        closeActivityStream();
        syncActivityStream();
      }
    }, 1000);
  };
}
function renderCodexActivity(root) {
  if (!activePlan || (!observesActivity(activePlan) && !activityEvents.length)) return;
  const card = message(root, "assistant", "", "executor-activity");
  const body = card.lastElementChild;
  add(body, "div", "Sagitta delegated workspace planning to Codex.", "activity-intro");
  const details = document.createElement("details");
  details.className = "activity-details";
  const phase = activePlan.status === "needs_input" ? "waiting for your answers" : "working";
  add(details, "summary", `Codex · ${phase} · ${activityEvents.length} activities`);
  const rows = add(details, "div", "", "activity-rows");
  activityEvents.forEach((activity) => {
    const row = add(rows, "div", "", `activity-row ${activity.status || "reported"}`);
    add(row, "span", activity.status === "failed" ? "×" : activity.status === "running" ? "·" : "✓", "activity-marker");
    const content = add(row, "div", "", "activity-content");
    add(content, "div", activity.title || "Codex activity");
    if (activity.detail) add(content, "small", activity.detail, "activity-detail");
  });
  body.append(details);
}
function renderPlannerRound(root) {
  const questions = activePlan?.response?.questions;
  if (mode !== "direct" || activePlan?.status !== "needs_input" || !Array.isArray(questions) || !questions.length) return;
  const card = message(root, "assistant", `This round has ${questions.length} decisions to settle before offline execution.`, "planner", { route: "direct" });
  const form = document.createElement("form");
  form.className = "planner-round";
  questions.forEach((question) => {
    const wrap = document.createElement("label");
    wrap.className = "planner-question";
    add(wrap, "p", question.question);
    add(wrap, "small", question.reason);
    const input = document.createElement("textarea");
    input.required = true;
    input.dataset.questionId = question.id;
    input.placeholder = "Enter an explicit answer, or switch to Sagitta for a recommendation";
    wrap.append(input);
    form.append(wrap);
  });
  const footer = add(form, "div", "", "planner-submit");
  add(footer, "span", submittingAnswers ? "Resuming the same Codex session…" : "Answers are written as one batch, then Codex resumes once.");
  const submit = add(footer, "button", submittingAnswers ? "Submitting…" : "Submit this round");
  submit.type = "submit";
  submit.disabled = submittingAnswers;
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (submittingAnswers || !activeTask) return;
    const answers = [...form.querySelectorAll("textarea")].map((input) => ({ id: input.dataset.questionId, answer: input.value.trim() }));
    if (answers.some((item) => !item.answer)) return notice("Answer every question in this round, or switch to Sagitta to discuss the trade-offs.");
    submittingAnswers = true;
    renderInteraction();
    try {
      await api(`/api/projects/${selected}/tasks/${activeTask.id}/answers`, jsonOptions({ answers }));
      await loadProject();
    } catch (error) {
      notice(error.message);
    } finally {
      submittingAnswers = false;
      renderInteraction();
    }
  };
  card.append(form);
}
function renderThread() {
  const root = $("#messages");
  root.replaceChildren();
  if (!selected) return add(root, "p", "Add a project from Finder first.", "empty-state");
  if (creatingTask) {
    return message(root, "assistant", "New task workspace. Describe the intended outcome and constraints. Sagitta can discuss it, or Direct can begin Codex planning immediately.", "planner");
  }
  if (!activeTask) return add(root, "p", "Use + beside a project to create an isolated task.", "empty-state");
  const messages = activeTask.messages || [];
  if (!messages.length) add(root, "p", "Start this task with Sagitta, or switch to Direct to create its Plan.", "empty-state");
  messages.forEach((entry) => message(root, entry.role, entry.content, "", entry.metadata || {}));
  (contextNotices.get(taskKey()) || []).forEach((entry) => message(root, "notice", entry.content, "context-notice"));
  renderCodexActivity(root);
  renderPlannerRound(root);
}
function renderComposer() {
  const form = $("#chat");
  const input = form.elements.content;
  const submit = form.querySelector("button");
  const directAnswersOpen = mode === "direct" && activePlan?.status === "needs_input";
  form.hidden = !selected || directAnswersOpen || (mode === "direct" && activePlan && activePlan.status !== "needs_input");
  if (form.hidden) return;
  input.disabled = busy;
  submit.disabled = busy;
  if (mode === "direct") {
    input.placeholder = activeTask ? "Describe the Plan for this task…" : "Describe the long-running task to plan…";
    submit.textContent = busy ? "Starting…" : "Start planning";
  } else {
    input.placeholder = creatingTask ? "Describe the new task for Sagitta…" : "Discuss this task with Sagitta…";
    submit.textContent = busy ? "Sending…" : creatingTask ? "Create task" : "Send";
  }
}
function renderInteraction() {
  renderTaskHeader();
  renderThread();
  renderComposer();
  syncActivityStream();
}

async function hydrateTask(taskId) {
  const [task, conversation] = await Promise.all([
    api(`/api/projects/${selected}/tasks/${taskId}`),
    api(`/api/projects/${selected}/tasks/${taskId}/conversation`),
  ]);
  activeTask = { ...task, messages: conversation.messages };
  activePlan = task.plan;
  if (activePlan) {
    activePlan = await api(`/api/projects/${selected}/plans/${activePlan.id}`);
    activeTask.plan = activePlan;
  }
}
async function loadProject() {
  if (!selected) return;
  const [status, taskList] = await Promise.all([
    api(`/api/projects/${selected}`),
    api(`/api/projects/${selected}/tasks`),
  ]);
  projectData = { ...status, tasks: taskList.tasks };
  if (activeTask && !projectData.tasks.some((task) => task.id === activeTask.id)) {
    activeTask = null;
    activePlan = null;
  }
  if (!activeTask && !creatingTask && projectData.tasks.length) await hydrateTask(projectData.tasks[0].id);
  else if (activeTask) await hydrateTask(activeTask.id);
  renderInteraction();
  renderVisualization();
  const { projects } = await api("/api/projects");
  renderProjects(projects);
}
async function selectTask(taskId) {
  closeActivityStream();
  creatingTask = false;
  await hydrateTask(taskId);
  renderInteraction();
  if (tab === "visualization") await renderVisualization();
  const { projects } = await api("/api/projects");
  renderProjects(projects);
}
function openNewTask() {
  closeActivityStream();
  activeTask = null;
  activePlan = null;
  creatingTask = true;
  setTab("interaction");
  renderInteraction();
  api("/api/projects").then(({ projects }) => renderProjects(projects)).catch((error) => notice(error.message));
}
async function createTask(title) {
  const task = await api(`/api/projects/${selected}/tasks`, jsonOptions({ title }));
  activeTask = task;
  activePlan = null;
  creatingTask = false;
  return task;
}
function confirmDeleteTask(task) {
  openModal({
    title: "Delete task",
    kicker: "LOCAL TASK DATA",
    content: (body) => {
      add(body, "p", `This deletes “${task.title || task.id}”, including its conversation, Plan package, IR, logs, Goal export, and future execution records. Project source files are unchanged.`);
      const actions = add(body, "div", "", "modal-actions");
      const cancel = add(actions, "button", "Cancel");
      cancel.type = "button";
      cancel.onclick = closeModal;
      const remove = add(actions, "button", "Delete task");
      remove.type = "button";
      remove.className = "danger-button";
      remove.onclick = async () => {
        remove.disabled = true;
        try {
          await api(`/api/projects/${selected}/tasks/${task.id}`, { method: "DELETE" });
          if (activeTask?.id === task.id) {
            activeTask = null;
            activePlan = null;
          }
          closeModal();
          await loadProject();
        } catch (error) {
          notice(error.message);
          remove.disabled = false;
        }
      };
    },
  });
}

function summaryMetric(root, label, value) {
  const card = add(root, "div", "", "metric");
  add(card, "span", label);
  add(card, "strong", value);
}
function renderMarkdown(container, content) {
  const lines = content.split("\n");
  let list = null;
  let code = null;
  lines.forEach((line) => {
    if (line.startsWith("```")) {
      if (code) { container.append(code); code = null; } else code = document.createElement("pre");
      return;
    }
    if (code) { code.textContent += (code.textContent ? "\n" : "") + line; return; }
    if (line.startsWith("### ")) { add(container, "h3", line.slice(4)); return; }
    if (line.startsWith("## ")) { add(container, "h2", line.slice(3)); return; }
    if (line.startsWith("# ")) { add(container, "h1", line.slice(2)); return; }
    if (line.startsWith("- ")) {
      if (!list) { list = document.createElement("ul"); container.append(list); }
      add(list, "li", line.slice(2));
      return;
    }
    list = null;
    if (line.trim()) add(container, "p", line);
  });
}
async function openArtifact(artifact) {
  const data = await api(`/api/projects/${selected}/plans/${activePlan.id}/artifacts/${encodeURIComponent(artifact.id)}`);
  openModal({
    title: data.title,
    kicker: data.path,
    content: (body) => {
      const rendered = document.createElement("article");
      rendered.className = "artifact-content";
      if (data.kind === "markdown" || data.kind === "goal") renderMarkdown(rendered, data.content);
      else { const pre = document.createElement("pre"); pre.textContent = data.content; rendered.append(pre); }
      body.append(rendered);
    },
  });
}
async function renderVisualization() {
  const content = $("#visual-content"), empty = $("#visual-empty");
  if (!activePlan) { content.hidden = true; empty.hidden = false; return; }
  content.hidden = false;
  empty.hidden = true;
  const summary = $("#plan-summary");
  summary.replaceChildren();
  summaryMetric(summary, "Status", statusText(activePlan.status));
  summaryMetric(summary, "Plan", activePlan.id);
  summaryMetric(summary, "Answered", String((activePlan.qa || []).length));
  const graph = $("#graph");
  graph.replaceChildren();
  (activePlan.graph?.nodes || []).forEach((node) => {
    const button = add(graph, "button", node.title, `node ${node.type}`);
    button.type = "button";
    button.onclick = () => document.querySelector(`[data-artifact="phase:${node.id}"]`)?.click();
  });
  (activePlan.graph?.edges || []).forEach((edge) => add(graph, "span", `${edge.from} → ${edge.to} · ${edge.label}`, "edge"));
  const artifacts = await api(`/api/projects/${selected}/plans/${activePlan.id}/artifacts`);
  const phases = $("#phase-list");
  phases.replaceChildren();
  artifacts.artifacts.filter((item) => item.id.startsWith("phase:")).forEach((artifact) => {
    const button = add(phases, "button", "", "phase-card");
    button.type = "button";
    button.dataset.artifact = artifact.id;
    add(button, "div", artifact.title);
    add(button, "small", artifact.path);
    button.onclick = () => openArtifact(artifact);
  });
  const artifactRoot = $("#artifacts");
  artifactRoot.replaceChildren();
  artifacts.artifacts.filter((item) => !item.id.startsWith("phase:")).forEach((artifact) => {
    const button = add(artifactRoot, "button", "", "artifact");
    button.type = "button";
    add(button, "div", artifact.title);
    add(button, "small", artifact.path);
    button.onclick = () => openArtifact(artifact);
  });
  const timeline = $("#event-timeline");
  timeline.replaceChildren();
  const events = artifacts.artifacts.find((item) => item.id === "events");
  if (events) {
    const eventData = await api(`/api/projects/${selected}/plans/${activePlan.id}/artifacts/events`);
    eventData.content.split("\n").filter(Boolean).slice(-20).forEach((raw) => {
      try {
        const event = JSON.parse(raw);
        const row = add(timeline, "div", "", "timeline-event");
        add(row, "time", event.at || "—");
        const detail = add(row, "div", "");
        add(detail, "strong", event.type || "event");
      } catch (_) { add(timeline, "div", "A planning event could not be read.", "message-status"); }
    });
  } else add(timeline, "p", "No planning events yet.", "empty-state");
  const goal = $("#goal-state");
  goal.replaceChildren();
  const state = projectData?.goal_state || { status: "absent", message: "—" };
  const line = add(goal, "div", "", "state-line");
  add(line, "strong", state.status);
  add(line, "span", state.message);
  const exportButton = $("#export-goal");
  exportButton.hidden = activePlan.status !== "ready";
  exportButton.onclick = async () => {
    try {
      await api(`/api/projects/${selected}/plans/${activePlan.id}/goal`, { method: "POST" });
      notice("Goal exported to the Task's Plan Package.");
      await loadProject();
    } catch (error) { notice(error.message); }
  };
}

async function addProject() {
  openModal({
    title: "Add project",
    kicker: "FINDER DIRECTORY",
    content: (body) => {
      add(body, "p", "Select an existing directory. Sagitta derives its label and internal ID and writes no registration files into the project.");
      const action = add(body, "button", "Choose project directory in Finder");
      action.onclick = async () => {
        action.disabled = true;
        try {
          const picked = await api("/api/system/select-directory", { method: "POST" });
          if (picked.status === "cancelled") return notice("No project directory selected.");
          const result = await api("/api/projects", jsonOptions({ workspace: picked.workspace }));
          selected = result.project.id;
          activeTask = null;
          activePlan = null;
          closeModal();
          await loadProjects();
        } catch (error) { notice(error.message); } finally { action.disabled = false; }
      };
    },
  });
}
async function openSettings() {
  const [settings, profile] = await Promise.all([api("/api/settings"), api("/api/profile")]);
  openModal({
    title: "Sagitta settings",
    kicker: "LOCAL ONLY",
    content: (body) => {
      const form = document.createElement("form");
      form.className = "modal-form";
      const field = (label, name, value, type = "text") => {
        const wrapper = document.createElement("label"); wrapper.textContent = label;
        const input = document.createElement(type === "textarea" ? "textarea" : "input");
        input.name = name; input.value = value || ""; if (type !== "textarea") input.type = type;
        wrapper.append(input); form.append(wrapper); return input;
      };
      field("Model", "model", settings.model);
      field("Base URL", "base_url", settings.base_url);
      const key = field("API Key (leave blank to keep the current key)", "api_key", "", "password");
      const clear = field("Clear saved API Key", "clear_api_key", "", "checkbox");
      clear.checked = false;
      field("Persona / Profile", "profile", profile.content, "textarea");
      const actions = add(form, "div", "", "modal-actions");
      const cancel = add(actions, "button", "Cancel"); cancel.type = "button"; cancel.onclick = closeModal;
      const save = add(actions, "button", "Save"); save.type = "submit";
      form.onsubmit = async (event) => {
        event.preventDefault(); save.disabled = true;
        try {
          const data = new FormData(form);
          await api("/api/settings", putOptions({ model: data.get("model"), base_url: data.get("base_url"), api_key: key.value || null, clear_api_key: clear.checked }));
          await api("/api/profile", putOptions({ content: data.get("profile") }));
          closeModal(); notice("Local settings saved.");
        } catch (error) { notice(error.message); } finally { save.disabled = false; }
      };
      body.append(form);
    },
  });
}
async function startDirectPlan(intent) {
  if (!activeTask) await createTask(intent);
  const plan = await api(`/api/projects/${selected}/tasks/${activeTask.id}/plans`, jsonOptions({ intent }));
  activePlan = plan;
  activeTask.plan = plan;
  activityEvents = [];
}
async function sendMessage(event) {
  event.preventDefault();
  if (!selected || busy) return;
  const form = event.currentTarget;
  const input = form.elements.content;
  const content = input.value.trim();
  if (!content) return;
  busy = true;
  renderInteraction();
  try {
    if (mode === "direct") {
      await startDirectPlan(content);
    } else {
      if (!activeTask) await createTask(content);
      await api(`/api/projects/${selected}/tasks/${activeTask.id}/messages`, jsonOptions({ content }));
    }
    input.value = "";
    await loadProject();
  } catch (error) { notice(error.message); } finally { busy = false; renderInteraction(); }
}
async function checkHealth() {
  try { await api("/api/health"); setBackendState(true, "Backend online"); }
  catch (_) { setBackendState(false, "Backend offline"); }
}

$("#close-modal").onclick = closeModal;
modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });
$("#add-project").onclick = addProject;
$("#open-settings").onclick = () => openSettings().catch((error) => notice(error.message));
$("#chat").onsubmit = sendMessage;
document.querySelectorAll("[data-mode]").forEach((button) => (button.onclick = () => setMode(button.dataset.mode)));
document.querySelectorAll("[data-tab]").forEach((button) => (button.onclick = () => setTab(button.dataset.tab)));
(async () => {
  await checkHealth();
  await loadProjects();
  setInterval(checkHealth, 5000);
})().catch((error) => notice(error.message));
