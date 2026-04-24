/**
 * AGV调度优化 — 指挥中心可视化系统
 * 独立设计，HUD 科幻风格
 */

const {
  buildTaskAssignments,
  computeTaskDeliveryTimes,
  getRunMaxTime,
  getPathPositionAtTime,
  getAgvCurrentTarget,
  summarizeAtTime,
  buildEventTimeline,
} = window.AnalysisUtils;
const {
  buildAlgorithmOptions,
  buildDataPath,
  buildSourceLabel,
} = window.DataSourceUtils;

const AGV_COLORS = [
  "#6366f1", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444",
  "#ec4899", "#8b5cf6", "#14b8a6", "#f97316", "#64748b",
  "#a78bfa", "#2dd4bf", "#fb923c", "#f87171", "#38bdf8",
  "#e879f9", "#4ade80", "#facc15", "#818cf8", "#34d399",
];

const THEME_COLORS = {
  mapBg: "#0c1220",
  obstacle: "#1a2438",
  obstacleBorder: "rgba(255,255,255,0.10)",
  startFill: "rgba(16, 185, 129, 0.1)",
  startStroke: "rgba(16, 185, 129, 0.3)",
  depotFill: "rgba(245, 158, 11, 0.12)",
  depotStroke: "rgba(245, 158, 11, 0.4)",
  depotText: "#f59e0b",
  grid: "rgba(255,255,255,0.08)",
  axisText: "#5a6a85",
  taskLabel: "#64748b",
  taskLabelFocused: "#dcf7ff",
  chartBg: "#0c1220",
  chartGrid: "rgba(255,255,255,0.05)",
  chartAxis: "#64748b",
  chartLine: "#00d4ff",
  chartLineGlow: "rgba(0, 212, 255, 0.2)",
  chartAreaTop: "rgba(0, 212, 255, 0.15)",
  chartAreaBottom: "rgba(124, 58, 237, 0.02)",
  chartPoint: "#00d4ff",
  chartPointGlow: "rgba(0, 212, 255, 0.12)",
  chartEmpty: "#334155",
};

let data = null;
let currentTime = 0;
let maxTime = 0;
let isPlaying = false;
let animFrameId = null;
let animProgress = 0;
let lastAnimTimestamp = null;
let playSpeed = 1000;
let eventTimeline = [];
let focusedAgvId = null;
let isolateFocus = false;
let showTrails = true;
let showTaskLabels = true;
let currentDataSource = "—";
let currentAlgorithmKey = "improved";
let activeTab = "agv";
const mapCanvas = document.getElementById("map-canvas");
const mapCtx = mapCanvas.getContext("2d");
const chartCanvas = document.getElementById("chart-canvas");
const chartCtx = chartCanvas.getContext("2d");

const btnPlay = document.getElementById("btn-play");
const iconPlay = document.getElementById("icon-play");
const iconPause = document.getElementById("icon-pause");
const btnStepFwd = document.getElementById("btn-step-fwd");
const btnStepBack = document.getElementById("btn-step-back");
const btnReset = document.getElementById("btn-reset");
const btnClearFocus = document.getElementById("btn-clear-focus");
const speedSelect = document.getElementById("speed-select");
const algorithmSelect = document.getElementById("algorithm-select");
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
const focusBadge = document.getElementById("focus-badge");
const tabBtns = document.querySelectorAll(".hud-tab");
const tabAgv = document.getElementById("tab-agv");
const tabEvents = document.getElementById("tab-events");
/* ========================================
   Event Listeners
   ======================================== */

algorithmSelect.addEventListener("change", async () => {
  currentAlgorithmKey = algorithmSelect.value;
  await loadSelectedSource();
});

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
  if (isPlaying) stop(); else play();
});

btnStepFwd.addEventListener("click", () => { stop(); stepForward(); });
btnStepBack.addEventListener("click", () => { stop(); stepBackward(); });
btnReset.addEventListener("click", () => { stop(); currentTime = 0; animProgress = 0; progressBar.value = 0; refreshFrame(); });

speedSelect.addEventListener("change", () => {
  playSpeed = parseInt(speedSelect.value, 10);
  // rAF loop uses playSpeed dynamically, no need to restart
});

progressBar.addEventListener("input", () => {
  currentTime = parseInt(progressBar.value, 10);
  animProgress = 0;
  refreshFrame();
});

window.addEventListener("resize", () => {
  resizeCanvases();
  if (data) { renderMap(); renderChart(); }
});

tabBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    if (tab === activeTab) return;
    activeTab = tab;
    tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    tabAgv.classList.toggle("hidden", tab !== "agv");
    tabEvents.classList.toggle("hidden", tab !== "events");
  });
});

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  switch (e.key) {
    case " ": e.preventDefault(); btnPlay.click(); break;
    case "ArrowRight": e.preventDefault(); btnStepFwd.click(); break;
    case "ArrowLeft": e.preventDefault(); btnStepBack.click(); break;
    case "Home": e.preventDefault(); btnReset.click(); break;
    case "End": e.preventDefault(); currentTime = maxTime; progressBar.value = maxTime; refreshFrame(); break;
  }
});

mapCanvas.addEventListener("mousemove", (event) => {
  if (!data) return;
  const rect = mapCanvas.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const gx = Math.floor((mx - origin.x) / cellSize);
  const gy = Math.floor((my - origin.y) / cellSize);

  if (gx < 0 || gy < 0 || gx >= data.map.width || gy >= data.map.height) {
    mapTooltip.classList.add("hidden"); return;
  }

  let info = `<strong>(${gx}, ${gy})</strong>`;
  const isObstacle = data.map.obstacles.some((p) => p[0] === gx && p[1] === gy);
  const dangerColor = "#ef4444";
  if (isObstacle) info += `<br><span style="color:${dangerColor}">障碍物</span>`;

  const task = data.tasks.find((item) => item.x === gx && item.y === gy);
  if (task) {
    const ownerId = data._taskOwners?.[task.id];
    const ownerColor = ownerId !== undefined ? getAgvColor(data._agvIndexById[ownerId]) : "#6366f1";
    info += `<br>任务 <span style="color:${ownerColor}">${task.id}</span> · W=${task.weight}kg · DD=${task.deadline}`;
  }

  for (let i = 0; i < data.agvs.length; i++) {
    const agv = data.agvs[i];
    const pos = getInterpolatedAgvPosition(agv, currentTime, animProgress);
    if (pos && Math.round(pos[0]) === gx && Math.round(pos[1]) === gy) {
      const color = getAgvColor(i);
      const focusTextColor = "#fff";
      info += `<br><span style="color:${color}">●</span> AGV-${agv.id}${focusedAgvId === agv.id ? ` <span style='color:${focusTextColor}'>(焦点)</span>` : ""}`;
    }
  }

  mapTooltip.innerHTML = info;
  mapTooltip.style.left = `${mx + 14}px`;
  mapTooltip.style.top = `${my - 8}px`;
  mapTooltip.classList.remove("hidden");
});

mapCanvas.addEventListener("mouseleave", () => mapTooltip.classList.add("hidden"));

mapCanvas.addEventListener("click", (event) => {
  if (!data) return;
  const rect = mapCanvas.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const gx = Math.floor((mx - origin.x) / cellSize);
  const gy = Math.floor((my - origin.y) / cellSize);

  for (let i = 0; i < data.agvs.length; i++) {
    const agv = data.agvs[i];
    const pos = getInterpolatedAgvPosition(agv, currentTime, animProgress);
    if (pos && Math.round(pos[0]) === gx && Math.round(pos[1]) === gy) {
      focusedAgvId = focusedAgvId === agv.id ? null : agv.id;
      renderMap(); updateInfoPanel(); return;
    }
  }
});

/* ========================================
   Data Loading
   ======================================== */

function loadData(json) {
  data = json;
  currentTime = 0;
  animProgress = 0;
  focusedAgvId = null;
  isolateFocus = false;
  toggleIsolateFocus.checked = false;

  maxTime = getRunMaxTime(data);
  for (const agv of data.agvs) {
    agv._taskDeliveryTimes = computeTaskDeliveryTimes(agv, data.tasks);
  }
  data._taskOwners = buildTaskAssignments(data);
  data._agvIndexById = {};
  data.agvs.forEach((agv, index) => { data._agvIndexById[agv.id] = index; });

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
  if (!scenarioName) return currentDataSource;
  if (currentDataSource === "最后运行结果") return "最后运行结果";
  return scenarioName;
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function fetchManifest() {
  try { return await fetchJson("data/manifest.json"); }
  catch (error) { return null; }
}

function updateAlgorithmOptions(options) {
  const currentValue = currentAlgorithmKey;
  algorithmSelect.innerHTML = "";
  for (const option of options) {
    const el = document.createElement("option");
    el.value = option.key;
    el.textContent = option.label;
    algorithmSelect.appendChild(el);
  }
  const availableKeys = options.map((o) => o.key);
  currentAlgorithmKey = availableKeys.includes(currentValue) ? currentValue : availableKeys[0];
  algorithmSelect.value = currentAlgorithmKey;
}

async function initializeDataSelectors() {
  const manifest = await fetchManifest();
  updateAlgorithmOptions(buildAlgorithmOptions(manifest));
}

async function loadLatestResult() {
  try {
    sampleSelect.value = "latest";
    currentDataSource = buildSourceLabel("latest");
    loadData(await fetchJson(buildDataPath(currentAlgorithmKey, "latest")));
  } catch (error) {
    currentDataSource = "—";
    alert(`加载 ${currentAlgorithmKey} 的最后运行结果失败: ${error.message}\n请先运行该算法生成 frontend/data/${currentAlgorithmKey}/result.json`);
  }
}

async function loadSampleScenario(scenarioId) {
  try {
    sampleSelect.value = String(scenarioId);
    currentDataSource = buildSourceLabel(String(scenarioId));
    loadData(await fetchJson(buildDataPath(currentAlgorithmKey, String(scenarioId))));
  } catch (error) {
    currentDataSource = "—";
    alert(`加载 ${currentAlgorithmKey} 的示例场景 ${scenarioId} 失败: ${error.message}`);
  }
}

async function loadSelectedSource() {
  if (sampleSelect.value === "latest") { await loadLatestResult(); return; }
  await loadSampleScenario(sampleSelect.value);
}

/* ========================================
   Canvas Sizing
   ======================================== */

function resizeCanvases() {
  const dpr = window.devicePixelRatio || 1;

  const mapWrapper = document.getElementById("map-stage");
  mapCanvas.width = mapWrapper.clientWidth * dpr;
  mapCanvas.height = mapWrapper.clientHeight * dpr;
  mapCanvas.style.width = `${mapWrapper.clientWidth}px`;
  mapCanvas.style.height = `${mapWrapper.clientHeight}px`;
  mapCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const chartSection = document.querySelector(".chart-section");
  if (chartSection) {
    const rect = chartSection.getBoundingClientRect();
    const cw = Math.max(200, Math.floor(rect.width));
    const ch = 160;
    chartCanvas.width = cw * dpr;
    chartCanvas.height = ch * dpr;
    chartCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
}

function refreshFrame() {
  updateTimeDisplay();
  renderMap();
  updateInfoPanel();
}

function getCellSize() {
  if (!data) return 20;
  const width = mapCanvas.clientWidth;
  const height = mapCanvas.clientHeight;
  const pad = 28;
  return Math.floor(Math.min((width - pad * 2) / data.map.width, (height - pad * 2) / data.map.height));
}

function getMapOrigin() {
  if (!data) return { x: 14, y: 14 };
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

function getInterpolatedAgvPosition(agv, timeStep, progress) {
  // progress: 0~1, interpolate between timeStep and timeStep+1
  const p0 = getPathPositionAtTime(agv, timeStep);
  if (progress <= 0) return p0;
  const p1 = getPathPositionAtTime(agv, timeStep + 1);
  if (!p1) return p0;
  const x = p0[0] + (p1[0] - p0[0]) * progress;
  const y = p0[1] + (p1[1] - p0[1]) * progress;
  return [x, y, timeStep + progress];
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
  if (!data || focusedAgvId === null) return null;
  return data.agvs.find((agv) => agv.id === focusedAgvId) || null;
}

/* ========================================
   Map Rendering
   ======================================== */

function renderMap() {
  if (!data) return;
  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const w = mapCanvas.clientWidth;
  const h = mapCanvas.clientHeight;

  const tc = THEME_COLORS;
  mapCtx.fillStyle = tc.mapBg;
  mapCtx.fillRect(0, 0, w, h);

  drawGrid(origin, cellSize);
  drawObstacles(origin, cellSize);
  drawStarts(origin, cellSize);
  drawDepot(origin, cellSize);
  drawTasks(origin, cellSize);
  drawAgvs(origin, cellSize);
  drawAxes(origin, cellSize);
}

function drawGrid(origin, cellSize) {
  mapCtx.strokeStyle = THEME_COLORS.grid;
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
  const r = Math.max(1, cellSize * 0.12);
  for (const [ox, oy] of data.map.obstacles) {
    const px = origin.x + ox * cellSize;
    const py = origin.y + oy * cellSize;
    mapCtx.fillStyle = THEME_COLORS.obstacle;
    roundRect(mapCtx, px + 1, py + 1, cellSize - 2, cellSize - 2, r);
    mapCtx.fill();
    mapCtx.strokeStyle = THEME_COLORS.obstacleBorder;
    mapCtx.lineWidth = 0.5;
    roundRect(mapCtx, px + 1, py + 1, cellSize - 2, cellSize - 2, r);
    mapCtx.stroke();
  }
}

function drawStarts(origin, cellSize) {
  const usedStarts = new Set(data.agvs.map((agv) => `${agv.start_pos[0]},${agv.start_pos[1]}`));
  const r = Math.max(1, cellSize * 0.1);
  for (const [sx, sy] of data.map.start_nodes) {
    if (!usedStarts.has(`${sx},${sy}`)) continue;
    const px = origin.x + sx * cellSize;
    const py = origin.y + sy * cellSize;
    mapCtx.fillStyle = THEME_COLORS.startFill;
    roundRect(mapCtx, px + 1, py + 1, cellSize - 2, cellSize - 2, r);
    mapCtx.fill();
    mapCtx.strokeStyle = THEME_COLORS.startStroke;
    mapCtx.lineWidth = 1;
    roundRect(mapCtx, px + 1, py + 1, cellSize - 2, cellSize - 2, r);
    mapCtx.stroke();
  }
}

function drawDepot(origin, cellSize) {
  const [dx, dy] = data.map.depot;
  const px = origin.x + dx * cellSize;
  const py = origin.y + dy * cellSize;
  const r = Math.max(1, cellSize * 0.1);
  const tc2 = THEME_COLORS;
  mapCtx.fillStyle = tc2.depotFill;
  roundRect(mapCtx, px + 1, py + 1, cellSize - 2, cellSize - 2, r);
  mapCtx.fill();
  mapCtx.strokeStyle = tc2.depotStroke;
  mapCtx.lineWidth = 1.5;
  roundRect(mapCtx, px + 1, py + 1, cellSize - 2, cellSize - 2, r);
  mapCtx.stroke();
  mapCtx.fillStyle = tc2.depotText;
  mapCtx.font = `bold ${Math.max(8, cellSize * 0.32)}px ${getCssVar("--font-sans")}`;
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
      mapCtx.globalAlpha = 0.12;
    } else if (delivered) {
      mapCtx.globalAlpha = 0.2;
    } else {
      mapCtx.globalAlpha = 1;
    }

    const ownerId = data._taskOwners?.[task.id];
    const ownerIndex = ownerId !== undefined ? data._agvIndexById?.[ownerId] : undefined;
    const taskColor = ownerIndex !== undefined ? getAgvColor(ownerIndex) : "#6366f1";

    if (!delivered && mapCtx.globalAlpha > 0.5) {
      mapCtx.beginPath();
      mapCtx.arc(px, py, radius + 5, 0, Math.PI * 2);
      mapCtx.fillStyle = taskColor + "18";
      mapCtx.fill();
    }

    mapCtx.beginPath();
    mapCtx.arc(px, py, radius, 0, Math.PI * 2);
    mapCtx.fillStyle = taskColor;
    mapCtx.fill();

    if (focusedTaskIds.has(task.id)) {
      mapCtx.beginPath();
      mapCtx.arc(px, py, radius + 4, 0, Math.PI * 2);
      mapCtx.strokeStyle = "rgba(255,255,255,0.6)";
      mapCtx.lineWidth = 1;
      mapCtx.stroke();
    }

    if (showTaskLabels && cellSize >= 14) {
      const tc3 = THEME_COLORS;
      mapCtx.fillStyle = focusedTaskIds.has(task.id) ? tc3.taskLabelFocused : tc3.taskLabel;
      mapCtx.font = `${Math.max(6, cellSize * 0.24)}px ${getCssVar("--font-mono")}`;
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
    if (!shouldRenderAgv(agv.id)) continue;

    const color = getAgvColor(index);
    const dimmed = shouldDimAgv(agv.id);
    const focused = isFocusedAgv(agv.id);
    const trailPoints = (agv.path || []).filter((point) => point[2] <= currentTime);
    const currentPos = getInterpolatedAgvPosition(agv, currentTime, animProgress);

    if (showTrails && (trailPoints.length > 0 || currentPos)) {
      mapCtx.beginPath();
      mapCtx.strokeStyle = color;
      mapCtx.globalAlpha = focused ? 0.75 : (dimmed ? 0.12 : 0.35);
      mapCtx.lineWidth = focused ? Math.max(1.8, cellSize * 0.09) : Math.max(1, cellSize * 0.06);
      mapCtx.lineJoin = "round";
      mapCtx.lineCap = "round";
      for (let i = 0; i < trailPoints.length; i++) {
        const px = origin.x + trailPoints[i][0] * cellSize + cellSize / 2;
        const py = origin.y + trailPoints[i][1] * cellSize + cellSize / 2;
        if (i === 0) mapCtx.moveTo(px, py); else mapCtx.lineTo(px, py);
      }
      if (currentPos) {
        const px = origin.x + currentPos[0] * cellSize + cellSize / 2;
        const py = origin.y + currentPos[1] * cellSize + cellSize / 2;
        mapCtx.lineTo(px, py);
      }
      mapCtx.stroke();
      mapCtx.globalAlpha = 1;
    }

    const pos = getInterpolatedAgvPosition(agv, currentTime, animProgress);
    if (!pos) continue;

    const px = origin.x + pos[0] * cellSize + cellSize / 2;
    const py = origin.y + pos[1] * cellSize + cellSize / 2;
    const radius = Math.max(4.5, cellSize * 0.3);

    if (focused || !dimmed) {
      mapCtx.beginPath();
      mapCtx.arc(px, py, focused ? radius + 10 : radius + 6, 0, Math.PI * 2);
      mapCtx.fillStyle = focused ? color + "20" : color + "10";
      mapCtx.fill();
    }

    if (focused) {
      mapCtx.beginPath();
      mapCtx.arc(px, py, radius + 4, 0, Math.PI * 2);
      mapCtx.strokeStyle = "rgba(255,255,255,0.5)";
      mapCtx.lineWidth = 1;
      mapCtx.stroke();
    }

    mapCtx.beginPath();
    mapCtx.arc(px, py, radius, 0, Math.PI * 2);
    mapCtx.fillStyle = color;
    mapCtx.globalAlpha = dimmed ? 0.3 : 1;
    mapCtx.fill();
    mapCtx.globalAlpha = 1;

    if (focused) {
      const target = getAgvCurrentTarget(agv, data.tasks, agv._taskDeliveryTimes, currentTime, data.map.depot);
      drawTargetMarker(target, origin, cellSize, color);
    }

    mapCtx.fillStyle = "#fff";
    mapCtx.font = `bold ${Math.max(6, cellSize * 0.26)}px ${getCssVar("--font-sans")}`;
    mapCtx.textAlign = "center";
    mapCtx.textBaseline = "middle";
    mapCtx.globalAlpha = dimmed ? 0.45 : 1;
    mapCtx.fillText(agv.id, px, py);
    mapCtx.globalAlpha = 1;
  }
}

function drawTargetMarker(target, origin, cellSize, color) {
  if (!target || target.x === undefined || target.y === undefined) return;
  const px = origin.x + target.x * cellSize + cellSize / 2;
  const py = origin.y + target.y * cellSize + cellSize / 2;
  const size = Math.max(5, cellSize * 0.25);
  mapCtx.save();
  mapCtx.strokeStyle = color;
  mapCtx.lineWidth = 1;
  mapCtx.setLineDash([3, 3]);
  mapCtx.beginPath();
  mapCtx.rect(px - size, py - size, size * 2, size * 2);
  mapCtx.stroke();
  mapCtx.restore();
}

function drawAxes(origin, cellSize) {
  mapCtx.fillStyle = THEME_COLORS.axisText;
  mapCtx.font = `${Math.max(6, cellSize * 0.26)}px ${getCssVar("--font-mono")}`;
  mapCtx.textAlign = "center";
  mapCtx.textBaseline = "top";
  const xStep = Math.max(1, Math.floor(data.map.width / 8));
  for (let x = 0; x < data.map.width; x += xStep) {
    mapCtx.fillText(x, origin.x + x * cellSize + cellSize / 2, origin.y + data.map.height * cellSize + 4);
  }
  mapCtx.textAlign = "right";
  mapCtx.textBaseline = "middle";
  const yStep = Math.max(1, Math.floor(data.map.height / 8));
  for (let y = 0; y < data.map.height; y += yStep) {
    mapCtx.fillText(y, origin.x - 4, origin.y + y * cellSize + cellSize / 2);
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/* ========================================
   Playback Controls
   ======================================== */

function play() {
  if (!data || currentTime >= maxTime) return;
  isPlaying = true;
  iconPlay.classList.add("hidden");
  iconPause.classList.remove("hidden");
  lastAnimTimestamp = null;
  animFrameId = requestAnimationFrame(animLoop);
}

function stop() {
  isPlaying = false;
  iconPlay.classList.remove("hidden");
  iconPause.classList.add("hidden");
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null; }
  lastAnimTimestamp = null;
}

function animLoop(timestamp) {
  if (!isPlaying) return;
  if (lastAnimTimestamp === null) lastAnimTimestamp = timestamp;
  const dt = timestamp - lastAnimTimestamp;
  lastAnimTimestamp = timestamp;

  animProgress += dt / playSpeed;

  while (animProgress >= 1 && currentTime < maxTime) {
    animProgress -= 1;
    currentTime += 1;
  }

  if (currentTime >= maxTime) {
    currentTime = maxTime;
    animProgress = 0;
    progressBar.value = currentTime;
    refreshFrame();
    stop();
    return;
  }

  progressBar.value = currentTime;
  refreshFrame();
  animFrameId = requestAnimationFrame(animLoop);
}

function stepForward() {
  if (!data || currentTime >= maxTime) return;
  currentTime += 1;
  animProgress = 0;
  progressBar.value = currentTime;
  refreshFrame();
}

function stepBackward() {
  if (!data || currentTime <= 0) return;
  currentTime -= 1;
  animProgress = 0;
  progressBar.value = currentTime;
  refreshFrame();
}

function updateTimeDisplay() {
  timeDisplay.textContent = `t = ${currentTime}`;
}

/* ========================================
   Info Panel
   ======================================== */

function updateRuntimeMeta() {
  if (!data) return;
  document.getElementById("run-scenario").textContent = data.meta?.scenario_name || "未命名场景";
  document.getElementById("run-algorithm").textContent = data.meta?.algorithm || "unknown";
  document.getElementById("run-seed").textContent = data.meta?.seed ?? "—";
  document.getElementById("run-source").textContent = currentDataSource;
}

function updateMetrics() {
  if (!data) return;
  const fitness = data.fitness;
  const fEl = document.getElementById("m-F");
  const nEl = document.getElementById("m-N");
  const dEl = document.getElementById("m-D");
  const tEl = document.getElementById("m-T");
  const cEl = document.getElementById("m-conflict");
  const rEl = document.getElementById("m-replan");

  fEl.textContent = fitness.F;
  nEl.textContent = fitness.N;
  dEl.textContent = fitness.D;
  tEl.textContent = fitness.T;
  cEl.textContent = fitness.conflict_count;
  rEl.textContent = fitness.replan_count;

  cEl.className = "kpi-num" + (fitness.conflict_count > 0 ? " danger" : "");
  rEl.className = "kpi-num" + (fitness.replan_count > 0 ? " warning" : "");
}

function updateInfoPanel() {
  if (!data) return;
  const summary = summarizeAtTime(data, currentTime);
  document.getElementById("m-total-tasks").textContent = summary.totalTasks;
  document.getElementById("m-completion-rate").textContent = `${summary.completionRate}%`;
  document.getElementById("m-active-agv").textContent = summary.activeAgvCount;
  document.getElementById("m-finished-agv").textContent = summary.completedAgvCount;

  focusBadge.textContent = focusedAgvId !== null ? `AGV-${focusedAgvId}` : "全部 AGV";

  renderAgvList();
  renderEventList();
}

function getAgvStatus(agv, pos) {
  if (!pos || currentTime === 0) return { status: "待命", statusClass: "idle" };
  if (currentTime >= agv.finish_time) return { status: "完成", statusClass: "done" };
  const rx = Math.round(pos[0]);
  const ry = Math.round(pos[1]);
  const serving = (data.tasks || []).some((task) => rx === task.x && ry === task.y);
  return serving ? { status: "服务中", statusClass: "serving" } : { status: "行驶中", statusClass: "moving" };
}

/* ========================================
   AGV List
   ======================================== */

function renderAgvList() {
  const list = document.getElementById("agv-list");
  list.innerHTML = "";

  if (!data || data.agvs.length === 0) {
    list.innerHTML = '<div class="empty-hint">暂无 AGV 数据</div>';
    return;
  }

  for (let index = 0; index < data.agvs.length; index++) {
    const agv = data.agvs[index];
    const color = getAgvColor(index);
    const pos = getInterpolatedAgvPosition(agv, currentTime, animProgress);
    const completedTasks = (agv.tasks || []).filter((taskId) =>
      agv._taskDeliveryTimes[taskId] !== undefined && currentTime >= agv._taskDeliveryTimes[taskId]).length;
    const target = getAgvCurrentTarget(agv, data.tasks, agv._taskDeliveryTimes, currentTime, data.map.depot);
    const { status, statusClass } = getAgvStatus(agv, pos);
    const progress = agv.tasks.length > 0 ? (completedTasks / agv.tasks.length) : 0;

    const item = document.createElement("div");
    item.className = "agv-item";
    item.style.setProperty("--item-color", color);
    if (focusedAgvId !== null && agv.id !== focusedAgvId) item.classList.add("dimmed");
    if (agv.id === focusedAgvId) item.classList.add("focused");

    item.innerHTML = `
      <div class="agv-stripe"></div>
      <div class="agv-body">
        <div class="agv-header">
          <span class="agv-id">AGV-${agv.id}</span>
          <span class="agv-status ${statusClass}">${status}</span>
        </div>
        <div class="agv-meta">
          <div class="agv-meta-row"><span class="agv-meta-label">位置</span><span class="agv-meta-value">${pos ? `(${pos[0].toFixed(1)},${pos[1].toFixed(1)})` : "—"}</span></div>
          <div class="agv-meta-row"><span class="agv-meta-label">目标</span><span class="agv-meta-value">${target.label}</span></div>
          <div class="agv-meta-row"><span class="agv-meta-label">任务</span><span class="agv-meta-value">${completedTasks}/${agv.tasks.length}</span></div>
        </div>
        <div class="agv-track"><div class="agv-fill" style="width: ${progress * 100}%"></div></div>
      </div>
    `;

    item.addEventListener("click", () => {
      focusedAgvId = focusedAgvId === agv.id ? null : agv.id;
      renderMap();
      updateInfoPanel();
    });

    list.appendChild(item);
  }
}

/* ========================================
   Event List
   ======================================== */

function renderEventList() {
  const container = document.getElementById("event-list");
  container.innerHTML = "";

  if (!data || eventTimeline.length === 0) {
    container.innerHTML = '<div class="empty-hint">暂无事件数据</div>';
    return;
  }

  const filtered = eventTimeline.filter((event) =>
    focusedAgvId === null || event.agvId === focusedAgvId);

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-hint">当前焦点 AGV 暂无事件</div>';
    return;
  }

  for (const event of filtered) {
    const isPast = event.time < currentTime;
    const item = document.createElement("div");
    item.className = `event-item ${isPast ? "past" : ""}`;

    const badgeClass = event.type === "task_complete" ? "task" : "agv";
    const badgeText = event.type === "task_complete" ? "任务完成" : "车辆完成";

    item.innerHTML = `
      <span class="event-time">t=${event.time}</span>
      <div class="event-text">
        <div class="event-title">${event.label}</div>
        <div class="event-detail">${event.detail}</div>
        <span class="event-tag ${badgeClass}">${badgeText}</span>
      </div>
    `;

    container.appendChild(item);
  }
}

/* ========================================
   Convergence Chart
   ======================================== */

function renderChart() {
  if (!data || !data.convergence || data.convergence.length === 0) {
    chartCtx.clearRect(0, 0, chartCanvas.clientWidth, chartCanvas.clientHeight);
    const tc = THEME_COLORS;
    chartCtx.fillStyle = tc.chartEmpty;
    chartCtx.font = "11px Inter, sans-serif";
    chartCtx.textAlign = "center";
    chartCtx.fillText("暂无收敛数据", chartCanvas.clientWidth / 2, chartCanvas.clientHeight / 2);
    chartCaption.textContent = "最优值 —";
    return;
  }

  const convergence = data.convergence;
  const width = chartCanvas.clientWidth;
  const height = chartCanvas.clientHeight;
  const pad = { top: 14, right: 12, bottom: 24, left: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const fValues = convergence.map((item) => item.best_fitness);
  const fMin = Math.min(...fValues);
  const fMax = Math.max(...fValues);
  const fRange = fMax - fMin || 1;
  const iterMax = convergence.length;

  if (width <= 0 || height <= 0 || plotW <= 10 || plotH <= 10) {
    const tcErr = THEME_COLORS;
    chartCtx.fillStyle = tcErr.chartEmpty;
    chartCtx.font = "11px Inter, sans-serif";
    chartCtx.textAlign = "center";
    chartCtx.fillText("画布尺寸异常", width / 2, height / 2);
    return;
  }

  const tc = THEME_COLORS;
  chartCtx.clearRect(0, 0, width, height);
  chartCtx.fillStyle = tc.chartBg;
  chartCtx.fillRect(0, 0, width, height);

  // Grid
  chartCtx.strokeStyle = tc.chartGrid;
  chartCtx.lineWidth = 0.5;
  const gridSteps = 5;
  for (let i = 0; i <= gridSteps; i++) {
    const yy = pad.top + (plotH / gridSteps) * i;
    chartCtx.beginPath();
    chartCtx.moveTo(pad.left, yy);
    chartCtx.lineTo(pad.left + plotW, yy);
    chartCtx.stroke();

    const val = fMax - (fRange / gridSteps) * i;
    chartCtx.fillStyle = tc.chartAxis;
    chartCtx.font = "8px JetBrains Mono, monospace";
    chartCtx.textAlign = "right";
    chartCtx.textBaseline = "middle";
    chartCtx.fillText(Math.round(val), pad.left - 6, yy);
  }

  // X labels
  chartCtx.textAlign = "center";
  chartCtx.textBaseline = "top";
  const xStep = Math.max(1, Math.floor(iterMax / 4));
  chartCtx.fillStyle = tc.chartAxis;
  chartCtx.font = "8px Inter, sans-serif";
  for (let i = 0; i < iterMax; i += xStep) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    chartCtx.fillText(convergence[i].iter, xx, pad.top + plotH + 5);
  }
  chartCtx.fillText(convergence[iterMax - 1].iter, pad.left + plotW, pad.top + plotH + 5);

  // Area
  const gradient = chartCtx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
  gradient.addColorStop(0, tc.chartAreaTop);
  gradient.addColorStop(1, tc.chartAreaBottom);

  chartCtx.beginPath();
  for (let i = 0; i < convergence.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    const yy = pad.top + plotH - ((convergence[i].best_fitness - fMin) / fRange) * plotH;
    if (i === 0) chartCtx.moveTo(xx, yy); else chartCtx.lineTo(xx, yy);
  }
  chartCtx.lineTo(pad.left + plotW, pad.top + plotH);
  chartCtx.lineTo(pad.left, pad.top + plotH);
  chartCtx.closePath();
  chartCtx.fillStyle = gradient;
  chartCtx.fill();

  // Glow line
  chartCtx.beginPath();
  for (let i = 0; i < convergence.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    const yy = pad.top + plotH - ((convergence[i].best_fitness - fMin) / fRange) * plotH;
    if (i === 0) chartCtx.moveTo(xx, yy); else chartCtx.lineTo(xx, yy);
  }
  chartCtx.strokeStyle = tc.chartLineGlow;
  chartCtx.lineWidth = 5;
  chartCtx.lineJoin = "round";
  chartCtx.stroke();

  // Main line
  chartCtx.beginPath();
  for (let i = 0; i < convergence.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    const yy = pad.top + plotH - ((convergence[i].best_fitness - fMin) / fRange) * plotH;
    if (i === 0) chartCtx.moveTo(xx, yy); else chartCtx.lineTo(xx, yy);
  }
  chartCtx.strokeStyle = tc.chartLine;
  chartCtx.lineWidth = 1.5;
  chartCtx.lineJoin = "round";
  chartCtx.stroke();

  // Last point
  const lastPoint = convergence[convergence.length - 1];
  const lastX = pad.left + plotW;
  const lastY = pad.top + plotH - ((lastPoint.best_fitness - fMin) / fRange) * plotH;

  chartCtx.beginPath();
  chartCtx.arc(lastX, lastY, 3, 0, Math.PI * 2);
  chartCtx.fillStyle = tc.chartPoint;
  chartCtx.fill();

  chartCtx.beginPath();
  chartCtx.arc(lastX, lastY, 6, 0, Math.PI * 2);
  chartCtx.fillStyle = tc.chartPointGlow;
  chartCtx.fill();

  chartCaption.textContent = `最优值 ${lastPoint.best_fitness}`;
}

/* ========================================
   Utilities
   ======================================== */

function getCssVar(name) {
  return getComputedStyle(document.body).getPropertyValue(name);
}

async function initializeApp() {
  resizeCanvases();
  await initializeDataSelectors();
  await loadSelectedSource();
}

resizeCanvases();
initializeApp();
