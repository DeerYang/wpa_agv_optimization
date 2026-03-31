/**
 * 多AGV调度优化 — 前端分析台
 *
 * 模块:
 *   DataLoader     — JSON 文件加载与预计算
 *   MapRenderer    — Canvas 栅格地图与焦点高亮
 *   AnimationCtrl  — 播放控制与时间步管理
 *   InfoPanel      — 运行摘要 / AGV 状态 / 时间轴
 *   ChartRenderer  — 收敛曲线绘制
 */

const {
  buildTaskAssignments,
  computeTaskDeliveryTimes,
  getPathPositionAtTime,
  getAgvCurrentTarget,
  summarizeAtTime,
  buildEventTimeline,
} = window.AnalysisUtils;

const AGV_COLORS = [
  "#6366f1", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444",
  "#ec4899", "#8b5cf6", "#14b8a6", "#f97316", "#64748b",
  "#a78bfa", "#2dd4bf", "#fb923c", "#f87171", "#38bdf8",
  "#e879f9", "#4ade80", "#facc15", "#818cf8", "#34d399",
];

let data = null;
let currentTime = 0;
let maxTime = 0;
let isPlaying = false;
let playInterval = null;
let playSpeed = 1000;
let eventTimeline = [];
let focusedAgvId = null;
let isolateFocus = false;
let showTrails = true;
let showTaskLabels = true;
let currentDataSource = "—";

const mapCanvas = document.getElementById("map-canvas");
const mapCtx = mapCanvas.getContext("2d");
const chartCanvas = document.getElementById("chart-canvas");
const chartCtx = chartCanvas.getContext("2d");

const btnPlay = document.getElementById("btn-play");
const btnStepFwd = document.getElementById("btn-step-fwd");
const btnStepBack = document.getElementById("btn-step-back");
const btnReset = document.getElementById("btn-reset");
const btnClearFocus = document.getElementById("btn-clear-focus");
const speedSelect = document.getElementById("speed-select");
const sampleSelect = document.getElementById("sample-select");
const progressBar = document.getElementById("progress-bar");
const timeDisplay = document.getElementById("time-display");
const timeMax = document.getElementById("time-max");
const scenarioBadge = document.getElementById("scenario-badge");
const mapTooltip = document.getElementById("map-tooltip");
const toggleTaskLabels = document.getElementById("toggle-task-labels");
const toggleTrails = document.getElementById("toggle-trails");
const toggleIsolateFocus = document.getElementById("toggle-isolate-focus");
const chartCaption = document.getElementById("chart-caption");
const eventStats = document.getElementById("event-stats");
const eventTimelineEl = document.getElementById("event-timeline");
const focusBadge = document.getElementById("focus-badge");
const focusDetail = document.getElementById("focus-detail");
const runSourceEl = document.getElementById("run-source");

sampleSelect.addEventListener("change", async () => {
  await loadSelectedSource();
});

toggleTaskLabels.addEventListener("change", () => {
  showTaskLabels = toggleTaskLabels.checked;
  renderMap();
});

toggleTrails.addEventListener("change", () => {
  showTrails = toggleTrails.checked;
  renderMap();
});

toggleIsolateFocus.addEventListener("change", () => {
  isolateFocus = toggleIsolateFocus.checked;
  renderMap();
  updateInfoPanel();
});

btnClearFocus.addEventListener("click", () => {
  focusedAgvId = null;
  isolateFocus = false;
  toggleIsolateFocus.checked = false;
  renderMap();
  updateInfoPanel();
});

btnPlay.addEventListener("click", () => {
  if (isPlaying) {
    stop();
  } else {
    play();
  }
});

btnStepFwd.addEventListener("click", () => {
  stop();
  stepForward();
});

btnStepBack.addEventListener("click", () => {
  stop();
  stepBackward();
});

btnReset.addEventListener("click", () => {
  stop();
  currentTime = 0;
  progressBar.value = 0;
  refreshFrame();
});

speedSelect.addEventListener("change", () => {
  playSpeed = parseInt(speedSelect.value, 10);
  if (isPlaying) {
    clearInterval(playInterval);
    playInterval = setInterval(tick, playSpeed);
  }
});

progressBar.addEventListener("input", () => {
  currentTime = parseInt(progressBar.value, 10);
  refreshFrame();
});

window.addEventListener("resize", () => {
  resizeCanvases();
  if (data) {
    renderMap();
    renderChart();
  }
});

mapCanvas.addEventListener("mousemove", (event) => {
  if (!data) {
    return;
  }

  const rect = mapCanvas.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const gx = Math.floor((mx - origin.x) / cellSize);
  const gy = Math.floor((my - origin.y) / cellSize);

  if (gx < 0 || gy < 0 || gx >= data.map.width || gy >= data.map.height) {
    mapTooltip.classList.add("hidden");
    return;
  }

  let info = `(${gx}, ${gy})`;
  const isObstacle = data.map.obstacles.some((point) => point[0] === gx && point[1] === gy);
  if (isObstacle) {
    info += " — 障碍物";
  }

  const task = data.tasks.find((item) => item.x === gx && item.y === gy);
  if (task) {
    info += ` — 任务${task.id} [W=${task.weight}kg, DD=${task.deadline}]`;
  }

  for (let index = 0; index < data.agvs.length; index++) {
    const agv = data.agvs[index];
    const pos = getAgvPositionAtTime(agv, currentTime);
    if (pos && pos[0] === gx && pos[1] === gy) {
      info += ` — AGV-${agv.id}`;
      if (focusedAgvId === agv.id) {
        info += "（焦点）";
      }
    }
  }

  mapTooltip.textContent = info;
  mapTooltip.style.left = `${mx + 14}px`;
  mapTooltip.style.top = `${my - 8}px`;
  mapTooltip.classList.remove("hidden");
});

mapCanvas.addEventListener("mouseleave", () => {
  mapTooltip.classList.add("hidden");
});

function loadData(json) {
  data = json;
  currentTime = 0;
  focusedAgvId = null;
  isolateFocus = false;
  toggleIsolateFocus.checked = false;

  maxTime = 0;
  for (const agv of data.agvs) {
    if ((agv.path || []).length > 0) {
      const lastTime = agv.path[agv.path.length - 1][2];
      if (lastTime > maxTime) {
        maxTime = lastTime;
      }
    }
    agv._taskDeliveryTimes = computeTaskDeliveryTimes(agv, data.tasks);
  }
  data._taskOwners = buildTaskAssignments(data);
  data._agvIndexById = {};
  data.agvs.forEach((agv, index) => {
    data._agvIndexById[agv.id] = index;
  });

  eventTimeline = buildEventTimeline(data);

  progressBar.max = maxTime;
  progressBar.value = 0;
  timeMax.textContent = `/ ${maxTime}`;

  scenarioBadge.textContent = buildScenarioBadgeText();
  scenarioBadge.classList.remove("hidden");

  resizeCanvases();
  stop();
  refreshAll();
}

function refreshAll() {
  updateRuntimeMeta();
  updateMetrics();
  renderChart();
  refreshFrame();
}

function buildScenarioBadgeText() {
  const scenarioName = data?.meta?.scenario_name;
  if (!scenarioName) {
    return currentDataSource;
  }
  if (currentDataSource === "最后运行结果") {
    return "最后运行结果";
  }
  return scenarioName;
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function loadLatestResult() {
  try {
    sampleSelect.value = "latest";
    currentDataSource = "最后运行结果";
    loadData(await fetchJson("data/result.json"));
  } catch (error) {
    currentDataSource = "—";
    alert(`加载最近结果失败: ${error.message}\n请先运行算法生成 frontend/data/result.json`);
  }
}

async function loadSampleScenario(scenarioId) {
  try {
    sampleSelect.value = String(scenarioId);
    currentDataSource = `示例场景 ${scenarioId}`;
    loadData(await fetchJson(`data/scenario-${scenarioId}.json`));
  } catch (error) {
    currentDataSource = "—";
    alert(`加载示例场景 ${scenarioId} 失败: ${error.message}`);
  }
}

async function loadSelectedSource() {
  if (sampleSelect.value === "latest") {
    await loadLatestResult();
    return;
  }

  await loadSampleScenario(sampleSelect.value);
}

function resizeCanvases() {
  const wrapper = document.getElementById("canvas-wrapper");
  const dpr = window.devicePixelRatio || 1;

  mapCanvas.width = wrapper.clientWidth * dpr;
  mapCanvas.height = wrapper.clientHeight * dpr;
  mapCanvas.style.width = `${wrapper.clientWidth}px`;
  mapCanvas.style.height = `${wrapper.clientHeight}px`;
  mapCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const chartWrapper = document.getElementById("chart-card");
  chartCanvas.width = chartWrapper.clientWidth * dpr;
  chartCanvas.height = 160 * dpr;
  chartCanvas.style.width = `${chartWrapper.clientWidth}px`;
  chartCanvas.style.height = "160px";
  chartCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function refreshFrame() {
  updateTimeDisplay();
  renderMap();
  updateInfoPanel();
}

function getCellSize() {
  if (!data) {
    return 20;
  }
  const width = mapCanvas.clientWidth;
  const height = mapCanvas.clientHeight;
  const pad = 40;
  return Math.floor(
    Math.min((width - pad * 2) / data.map.width, (height - pad * 2) / data.map.height),
  );
}

function getMapOrigin() {
  if (!data) {
    return { x: 20, y: 20 };
  }
  const cellSize = getCellSize();
  return {
    x: Math.floor((mapCanvas.clientWidth - (data.map.width * cellSize)) / 2),
    y: Math.floor((mapCanvas.clientHeight - (data.map.height * cellSize)) / 2),
  };
}

function getAgvColor(index) {
  return AGV_COLORS[index % AGV_COLORS.length];
}

function getAgvPositionAtTime(agv, timeStep) {
  return getPathPositionAtTime(agv, timeStep);
}

function isFocusedAgv(agvId) {
  return focusedAgvId !== null && focusedAgvId === agvId;
}

function shouldDimAgv(agvId) {
  return focusedAgvId !== null && focusedAgvId !== agvId;
}

function shouldRenderAgv(agvId) {
  return !(isolateFocus && focusedAgvId !== null && focusedAgvId !== agvId);
}

function getFocusedAgv() {
  if (!data || focusedAgvId === null) {
    return null;
  }
  return data.agvs.find((agv) => agv.id === focusedAgvId) || null;
}

function renderMap() {
  if (!data) {
    return;
  }

  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const width = mapCanvas.clientWidth;
  const height = mapCanvas.clientHeight;

  mapCtx.fillStyle = "#12141f";
  mapCtx.fillRect(0, 0, width, height);

  drawGrid(origin, cellSize);
  drawObstacles(origin, cellSize);
  drawStarts(origin, cellSize);
  drawDepot(origin, cellSize);
  drawTasks(origin, cellSize);
  drawAgvs(origin, cellSize);
  drawAxes(origin, cellSize);
}

function drawGrid(origin, cellSize) {
  mapCtx.strokeStyle = "#1e2035";
  mapCtx.lineWidth = 0.5;
  for (let x = 0; x <= data.map.width; x++) {
    mapCtx.beginPath();
    mapCtx.moveTo(origin.x + x * cellSize, origin.y);
    mapCtx.lineTo(origin.x + x * cellSize, origin.y + data.map.height * cellSize);
    mapCtx.stroke();
  }
  for (let y = 0; y <= data.map.height; y++) {
    mapCtx.beginPath();
    mapCtx.moveTo(origin.x, origin.y + y * cellSize);
    mapCtx.lineTo(origin.x + data.map.width * cellSize, origin.y + y * cellSize);
    mapCtx.stroke();
  }
}

function drawObstacles(origin, cellSize) {
  for (const [ox, oy] of data.map.obstacles) {
    const px = origin.x + ox * cellSize;
    const py = origin.y + oy * cellSize;
    mapCtx.fillStyle = "#283040";
    mapCtx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
    mapCtx.strokeStyle = "#3a4560";
    mapCtx.strokeRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
  }
}

function drawStarts(origin, cellSize) {
  const usedStarts = new Set(data.agvs.map((agv) => `${agv.start_pos[0]},${agv.start_pos[1]}`));
  for (const [sx, sy] of data.map.start_nodes) {
    if (!usedStarts.has(`${sx},${sy}`)) {
      continue;
    }
    const px = origin.x + sx * cellSize;
    const py = origin.y + sy * cellSize;
    mapCtx.fillStyle = "rgba(34, 197, 94, 0.2)";
    mapCtx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
    mapCtx.strokeStyle = "#22c55e";
    mapCtx.lineWidth = 1;
    mapCtx.strokeRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
  }
}

function drawDepot(origin, cellSize) {
  const [dx, dy] = data.map.depot;
  const px = origin.x + dx * cellSize;
  const py = origin.y + dy * cellSize;
  mapCtx.fillStyle = "rgba(245, 158, 11, 0.25)";
  mapCtx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
  mapCtx.strokeStyle = "#f59e0b";
  mapCtx.lineWidth = 1.5;
  mapCtx.strokeRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
  mapCtx.fillStyle = "#f59e0b";
  mapCtx.font = `bold ${Math.max(8, cellSize * 0.35)}px ${getCssVar("--font-sans")}`;
  mapCtx.textAlign = "center";
  mapCtx.textBaseline = "middle";
  mapCtx.fillText("D", px + cellSize / 2, py + cellSize / 2);
}

function drawTasks(origin, cellSize) {
  const focusedAgv = getFocusedAgv();
  const focusedTaskIds = new Set((focusedAgv && focusedAgv.tasks) || []);

  for (const task of data.tasks) {
    const px = origin.x + task.x * cellSize + cellSize / 2;
    const py = origin.y + task.y * cellSize + cellSize / 2;
    const radius = Math.max(3, cellSize * 0.22);
    const delivered = data.agvs.some((agv) =>
      agv._taskDeliveryTimes[task.id] !== undefined && currentTime >= agv._taskDeliveryTimes[task.id]);

    if (focusedAgvId !== null && !focusedTaskIds.has(task.id)) {
      mapCtx.globalAlpha = 0.18;
    } else if (delivered) {
      mapCtx.globalAlpha = 0.3;
    } else {
      mapCtx.globalAlpha = 1;
    }

    const ownerId = data._taskOwners?.[task.id];
    const ownerIndex = ownerId !== undefined ? data._agvIndexById?.[ownerId] : undefined;
    const taskColor = ownerIndex !== undefined ? getAgvColor(ownerIndex) : "#6366f1";

    mapCtx.beginPath();
    mapCtx.arc(px, py, radius, 0, Math.PI * 2);
    mapCtx.fillStyle = taskColor;
    mapCtx.fill();

    if (focusedTaskIds.has(task.id)) {
      mapCtx.beginPath();
      mapCtx.arc(px, py, radius + 4, 0, Math.PI * 2);
      mapCtx.strokeStyle = "rgba(255, 255, 255, 0.82)";
      mapCtx.lineWidth = 1.5;
      mapCtx.stroke();
    }

    if (showTaskLabels && cellSize >= 18) {
      mapCtx.fillStyle = focusedTaskIds.has(task.id) ? "#dcf7ff" : "#c7d0e8";
      mapCtx.font = `${Math.max(7, cellSize * 0.28)}px ${getCssVar("--font-mono")}`;
      mapCtx.textAlign = "center";
      mapCtx.textBaseline = "bottom";
      mapCtx.fillText(task.id, px, py - radius - 2);
    }

    mapCtx.globalAlpha = 1;
  }
}

function drawAgvs(origin, cellSize) {
  for (let index = 0; index < data.agvs.length; index++) {
    const agv = data.agvs[index];
    if (!shouldRenderAgv(agv.id)) {
      continue;
    }

    const color = getAgvColor(index);
    const dimmed = shouldDimAgv(agv.id);
    const focused = isFocusedAgv(agv.id);
    const trailPoints = (agv.path || []).filter((point) => point[2] <= currentTime);

    if (showTrails && trailPoints.length > 1) {
      mapCtx.beginPath();
      mapCtx.strokeStyle = color;
      mapCtx.globalAlpha = focused ? 0.8 : (dimmed ? 0.12 : 0.32);
      mapCtx.lineWidth = focused ? Math.max(2.5, cellSize * 0.12) : Math.max(1.5, cellSize * 0.08);
      mapCtx.lineJoin = "round";
      mapCtx.lineCap = "round";
      for (let i = 0; i < trailPoints.length; i++) {
        const px = origin.x + trailPoints[i][0] * cellSize + cellSize / 2;
        const py = origin.y + trailPoints[i][1] * cellSize + cellSize / 2;
        if (i === 0) {
          mapCtx.moveTo(px, py);
        } else {
          mapCtx.lineTo(px, py);
        }
      }
      mapCtx.stroke();
      mapCtx.globalAlpha = 1;
    }

    const pos = getAgvPositionAtTime(agv, currentTime);
    if (!pos) {
      continue;
    }

    const px = origin.x + pos[0] * cellSize + cellSize / 2;
    const py = origin.y + pos[1] * cellSize + cellSize / 2;
    const radius = Math.max(4, cellSize * 0.3);

    mapCtx.beginPath();
    mapCtx.arc(px, py, focused ? radius + 6 : radius + 3, 0, Math.PI * 2);
    mapCtx.fillStyle = focused ? `${color}55` : `${color}30`;
    mapCtx.fill();

    mapCtx.beginPath();
    mapCtx.arc(px, py, radius, 0, Math.PI * 2);
    mapCtx.fillStyle = color;
    mapCtx.globalAlpha = dimmed ? 0.45 : 1;
    mapCtx.fill();
    mapCtx.globalAlpha = 1;

    if (focused) {
      mapCtx.beginPath();
      mapCtx.arc(px, py, radius + 3, 0, Math.PI * 2);
      mapCtx.strokeStyle = "#ffffff";
      mapCtx.lineWidth = 1.5;
      mapCtx.stroke();

      const target = getAgvCurrentTarget(
        agv,
        data.tasks,
        agv._taskDeliveryTimes,
        currentTime,
        data.map.depot,
      );
      drawTargetMarker(target, origin, cellSize, color);
    }

    mapCtx.fillStyle = "#fff";
    mapCtx.font = `bold ${Math.max(7, cellSize * 0.28)}px ${getCssVar("--font-sans")}`;
    mapCtx.textAlign = "center";
    mapCtx.textBaseline = "middle";
    mapCtx.fillText(agv.id, px, py);
  }
}

function drawTargetMarker(target, origin, cellSize, color) {
  if (!target || target.x === undefined || target.y === undefined) {
    return;
  }
  const px = origin.x + target.x * cellSize + cellSize / 2;
  const py = origin.y + target.y * cellSize + cellSize / 2;
  const size = Math.max(7, cellSize * 0.32);

  mapCtx.save();
  mapCtx.strokeStyle = color;
  mapCtx.lineWidth = 1.5;
  mapCtx.setLineDash([4, 3]);
  mapCtx.beginPath();
  mapCtx.rect(px - size, py - size, size * 2, size * 2);
  mapCtx.stroke();
  mapCtx.restore();
}

function drawAxes(origin, cellSize) {
  mapCtx.fillStyle = "#4a5070";
  mapCtx.font = `${Math.max(7, cellSize * 0.3)}px ${getCssVar("--font-mono")}`;
  mapCtx.textAlign = "center";
  mapCtx.textBaseline = "top";
  for (let x = 0; x < data.map.width; x += Math.max(1, Math.floor(data.map.width / 10))) {
    mapCtx.fillText(x, origin.x + x * cellSize + cellSize / 2, origin.y + data.map.height * cellSize + 4);
  }
  mapCtx.textAlign = "right";
  mapCtx.textBaseline = "middle";
  for (let y = 0; y < data.map.height; y += Math.max(1, Math.floor(data.map.height / 10))) {
    mapCtx.fillText(y, origin.x - 5, origin.y + y * cellSize + cellSize / 2);
  }
}

function play() {
  if (!data) {
    return;
  }
  isPlaying = true;
  btnPlay.textContent = "⏸";
  playInterval = setInterval(tick, playSpeed);
}

function stop() {
  isPlaying = false;
  btnPlay.textContent = "▶";
  if (playInterval) {
    clearInterval(playInterval);
    playInterval = null;
  }
}

function tick() {
  if (currentTime >= maxTime) {
    stop();
    return;
  }
  stepForward();
}

function stepForward() {
  if (!data || currentTime >= maxTime) {
    return;
  }
  currentTime += 1;
  progressBar.value = currentTime;
  refreshFrame();
}

function stepBackward() {
  if (!data || currentTime <= 0) {
    return;
  }
  currentTime -= 1;
  progressBar.value = currentTime;
  refreshFrame();
}

function updateTimeDisplay() {
  timeDisplay.textContent = `t = ${currentTime}`;
}

function updateRuntimeMeta() {
  if (!data) {
    return;
  }
  document.getElementById("run-scenario").textContent = data.meta?.scenario_name || "未命名场景";
  document.getElementById("run-algorithm").textContent = data.meta?.algorithm || "unknown";
  document.getElementById("run-seed").textContent = data.meta?.seed ?? "—";
  runSourceEl.textContent = currentDataSource;
}

function updateMetrics() {
  if (!data) {
    return;
  }
  const fitness = data.fitness;
  document.getElementById("m-F").textContent = fitness.F;
  document.getElementById("m-N").textContent = fitness.N;
  document.getElementById("m-D").textContent = fitness.D;
  document.getElementById("m-T").textContent = fitness.T;
  document.getElementById("m-conflict").textContent = fitness.conflict_count;
  document.getElementById("m-replan").textContent = fitness.replan_count;
}

function updateInfoPanel() {
  if (!data) {
    return;
  }

  const summary = summarizeAtTime(data, currentTime);
  document.getElementById("m-total-tasks").textContent = summary.totalTasks;
  document.getElementById("m-completion-rate").textContent = `${summary.completionRate}%`;
  document.getElementById("m-active-agv").textContent = summary.activeAgvCount;
  document.getElementById("m-finished-agv").textContent = summary.completedAgvCount;

  const focusedAgv = getFocusedAgv();
  focusBadge.textContent = focusedAgv ? `AGV-${focusedAgv.id}` : "全部 AGV";
  focusDetail.textContent = focusedAgv
    ? buildFocusedAgvDetail(focusedAgv)
    : "点击下方 AGV 行可进入焦点模式，并在地图上单独追踪其路径与目标。";

  renderAgvTable();
  renderTimeline();
}

function renderAgvTable() {
  const tbody = document.getElementById("agv-table-body");
  tbody.innerHTML = "";

  for (let index = 0; index < data.agvs.length; index++) {
    const agv = data.agvs[index];
    const color = getAgvColor(index);
    const pos = getAgvPositionAtTime(agv, currentTime);
    const completedTasks = (agv.tasks || []).filter((taskId) =>
      agv._taskDeliveryTimes[taskId] !== undefined && currentTime >= agv._taskDeliveryTimes[taskId]).length;
    const target = getAgvCurrentTarget(
      agv,
      data.tasks,
      agv._taskDeliveryTimes,
      currentTime,
      data.map.depot,
    );
    const { status, statusClass } = getAgvStatus(agv, pos);

    const row = document.createElement("tr");
    if (focusedAgvId !== null && agv.id !== focusedAgvId) {
      row.classList.add("row-dim");
    }
    if (agv.id === focusedAgvId) {
      row.classList.add("row-focused");
    }

    row.innerHTML = `
      <td><span class="agv-color-dot" style="background:${color}"></span>${agv.id}</td>
      <td>${pos ? `(${pos[0]},${pos[1]})` : "—"}</td>
      <td><span class="target-tag">${target.label}</span></td>
      <td>${completedTasks}/${agv.tasks.length}</td>
      <td>${agv.load}kg</td>
      <td><span class="status-tag ${statusClass}">${status}</span></td>
    `;

    row.addEventListener("click", () => {
      focusedAgvId = focusedAgvId === agv.id ? null : agv.id;
      renderMap();
      updateInfoPanel();
    });

    tbody.appendChild(row);
  }
}

function getAgvStatus(agv, pos) {
  if (!pos || currentTime === 0) {
    return { status: "待命", statusClass: "idle" };
  }
  if (currentTime >= agv.finish_time) {
    return { status: "完成", statusClass: "done" };
  }

  const serving = (data.tasks || []).some((task) => pos[0] === task.x && pos[1] === task.y);
  return serving
    ? { status: "服务中", statusClass: "serving" }
    : { status: "行驶中", statusClass: "moving" };
}

function buildFocusedAgvDetail(agv) {
  const target = getAgvCurrentTarget(
    agv,
    data.tasks,
    agv._taskDeliveryTimes,
    currentTime,
    data.map.depot,
  );
  const pos = getAgvPositionAtTime(agv, currentTime);
  const completedTasks = (agv.tasks || []).filter((taskId) =>
    agv._taskDeliveryTimes[taskId] !== undefined && currentTime >= agv._taskDeliveryTimes[taskId]).length;
  const status = getAgvStatus(agv, pos).status;

  return `AGV-${agv.id} 当前位于 ${pos ? `(${pos[0]}, ${pos[1]})` : "未知位置"}，状态为 ${status}，已完成 ${completedTasks}/${agv.tasks.length} 个任务，当前目标为 ${target.label}。`;
}

function renderTimeline() {
  if (!data || eventTimeline.length === 0) {
    eventTimelineEl.innerHTML = '<div class="empty-hint timeline-empty">暂无事件数据</div>';
    eventStats.textContent = "0 条事件";
    return;
  }

  const filtered = eventTimeline.filter((event) =>
    focusedAgvId === null || event.agvId === focusedAgvId);
  eventStats.textContent = `${filtered.length} 条事件`;

  if (filtered.length === 0) {
    eventTimelineEl.innerHTML = '<div class="empty-hint timeline-empty">当前焦点 AGV 暂无事件</div>';
    return;
  }

  eventTimelineEl.innerHTML = "";
  for (const event of filtered) {
    const item = document.createElement("div");
    const eventClass = event.time < currentTime
      ? "event-past"
      : (event.time === currentTime ? "event-current" : "");
    item.className = `timeline-item ${eventClass} ${focusedAgvId !== null ? "event-focus" : ""}`.trim();
    item.innerHTML = `
      <div class="timeline-time">t=${event.time}</div>
      <div>
        <div class="timeline-title">${event.label}</div>
        <div class="timeline-detail">${event.detail}</div>
        <span class="timeline-badge">${event.type === "task_complete" ? "任务完成" : "车辆完成"}</span>
      </div>
    `;
    eventTimelineEl.appendChild(item);
  }
}

function renderChart() {
  if (!data || !data.convergence || data.convergence.length === 0) {
    chartCtx.clearRect(0, 0, chartCanvas.clientWidth, 160);
    chartCtx.fillStyle = "#4a5070";
    chartCtx.font = "12px Inter, sans-serif";
    chartCtx.textAlign = "center";
    chartCtx.fillText("暂无收敛数据", chartCanvas.clientWidth / 2, 80);
    chartCaption.textContent = "最优值 —";
    return;
  }

  const convergence = data.convergence;
  const width = chartCanvas.clientWidth;
  const height = 160;
  const pad = { top: 20, right: 16, bottom: 28, left: 50 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const fValues = convergence.map((item) => item.best_fitness);
  const fMin = Math.min(...fValues);
  const fMax = Math.max(...fValues);
  const fRange = fMax - fMin || 1;
  const iterMax = convergence.length;

  chartCtx.clearRect(0, 0, width, height);
  chartCtx.fillStyle = "#161822";
  chartCtx.fillRect(0, 0, width, height);

  chartCtx.strokeStyle = "#1e2035";
  chartCtx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const yy = pad.top + (plotHeight / 4) * i;
    chartCtx.beginPath();
    chartCtx.moveTo(pad.left, yy);
    chartCtx.lineTo(pad.left + plotWidth, yy);
    chartCtx.stroke();

    const val = fMax - (fRange / 4) * i;
    chartCtx.fillStyle = "#4a5070";
    chartCtx.font = "9px JetBrains Mono, monospace";
    chartCtx.textAlign = "right";
    chartCtx.textBaseline = "middle";
    chartCtx.fillText(Math.round(val), pad.left - 6, yy);
  }

  chartCtx.textAlign = "center";
  chartCtx.textBaseline = "top";
  const xStep = Math.max(1, Math.floor(iterMax / 5));
  for (let i = 0; i < iterMax; i += xStep) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotWidth;
    chartCtx.fillText(convergence[i].iter, xx, pad.top + plotHeight + 6);
  }
  chartCtx.fillText(convergence[iterMax - 1].iter, pad.left + plotWidth, pad.top + plotHeight + 6);

  chartCtx.fillStyle = "#636882";
  chartCtx.font = "9px Inter, sans-serif";
  chartCtx.save();
  chartCtx.translate(12, pad.top + plotHeight / 2);
  chartCtx.rotate(-Math.PI / 2);
  chartCtx.textAlign = "center";
  chartCtx.fillText("F", 0, 0);
  chartCtx.restore();
  chartCtx.textAlign = "center";
  chartCtx.fillText("迭代", pad.left + plotWidth / 2, height - 4);

  const gradient = chartCtx.createLinearGradient(0, pad.top, 0, pad.top + plotHeight);
  gradient.addColorStop(0, "rgba(99, 102, 241, 0.25)");
  gradient.addColorStop(1, "rgba(99, 102, 241, 0.02)");

  chartCtx.beginPath();
  for (let i = 0; i < convergence.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotWidth;
    const yy = pad.top + plotHeight - ((convergence[i].best_fitness - fMin) / fRange) * plotHeight;
    if (i === 0) {
      chartCtx.moveTo(xx, yy);
    } else {
      chartCtx.lineTo(xx, yy);
    }
  }
  chartCtx.lineTo(pad.left + plotWidth, pad.top + plotHeight);
  chartCtx.lineTo(pad.left, pad.top + plotHeight);
  chartCtx.closePath();
  chartCtx.fillStyle = gradient;
  chartCtx.fill();

  chartCtx.beginPath();
  for (let i = 0; i < convergence.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotWidth;
    const yy = pad.top + plotHeight - ((convergence[i].best_fitness - fMin) / fRange) * plotHeight;
    if (i === 0) {
      chartCtx.moveTo(xx, yy);
    } else {
      chartCtx.lineTo(xx, yy);
    }
  }
  chartCtx.strokeStyle = "#6366f1";
  chartCtx.lineWidth = 2;
  chartCtx.lineJoin = "round";
  chartCtx.stroke();

  const lastPoint = convergence[convergence.length - 1];
  const lastX = pad.left + plotWidth;
  const lastY = pad.top + plotHeight - ((lastPoint.best_fitness - fMin) / fRange) * plotHeight;
  chartCtx.beginPath();
  chartCtx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
  chartCtx.fillStyle = "#06b6d4";
  chartCtx.fill();

  chartCtx.fillStyle = "#06b6d4";
  chartCtx.font = "bold 10px JetBrains Mono, monospace";
  chartCtx.textAlign = "right";
  chartCtx.textBaseline = "bottom";
  chartCtx.fillText(lastPoint.best_fitness, lastX - 6, lastY - 5);
  chartCaption.textContent = `最优值 ${lastPoint.best_fitness}`;
}

function getCssVar(name) {
  return getComputedStyle(document.body).getPropertyValue(name);
}

resizeCanvases();
loadSelectedSource();
