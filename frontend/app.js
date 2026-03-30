/**
 * 多AGV调度优化 — 前端可视化回放系统
 *
 * 模块:
 *   DataLoader     — JSON 文件加载与示例数据
 *   MapRenderer    — Canvas 栅格地图渲染
 *   AnimationCtrl  — 播放控制与时间步管理
 *   InfoPanel      — 右侧信息面板更新
 *   ChartRenderer  — 收敛曲线绘制
 */

// ========== AGV Colors ==========
const AGV_COLORS = [
  '#6366f1', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444',
  '#ec4899', '#8b5cf6', '#14b8a6', '#f97316', '#64748b',
  '#a78bfa', '#2dd4bf', '#fb923c', '#f87171', '#38bdf8',
  '#e879f9', '#4ade80', '#facc15', '#818cf8', '#34d399',
];

// ========== State ==========
let data = null;          // loaded JSON
let currentTime = 0;      // current animation time step
let maxTime = 0;          // max time across all AGV paths
let isPlaying = false;
let playInterval = null;
let playSpeed = 1000;

// ========== DOM Elements ==========
const mapCanvas = document.getElementById('map-canvas');
const mapCtx = mapCanvas.getContext('2d');
const chartCanvas = document.getElementById('chart-canvas');
const chartCtx = chartCanvas.getContext('2d');

const btnPlay = document.getElementById('btn-play');
const btnStepFwd = document.getElementById('btn-step-fwd');
const btnStepBack = document.getElementById('btn-step-back');
const btnReset = document.getElementById('btn-reset');
const btnLoadDemo = document.getElementById('btn-load-demo');
const speedSelect = document.getElementById('speed-select');
const progressBar = document.getElementById('progress-bar');
const timeDisplay = document.getElementById('time-display');
const timeMax = document.getElementById('time-max');
const jsonFileInput = document.getElementById('json-file-input');
const scenarioBadge = document.getElementById('scenario-badge');
const mapTooltip = document.getElementById('map-tooltip');

// ========== Data Loading ==========
jsonFileInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const parsed = JSON.parse(ev.target.result);
      loadData(parsed);
    } catch (err) {
      alert('JSON 解析失败: ' + err.message);
    }
  };
  reader.readAsText(file);
});

btnLoadDemo.addEventListener('click', async () => {
  try {
    const resp = await fetch('data/result.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const parsed = await resp.json();
    loadData(parsed);
  } catch (err) {
    alert('加载示例数据失败: ' + err.message + '\n请先运行算法生成 frontend/data/result.json');
  }
});

function loadData(json) {
  data = json;
  currentTime = 0;

  // compute maxTime
  maxTime = 0;
  for (const agv of data.agvs) {
    if (agv.path.length > 0) {
      const lastT = agv.path[agv.path.length - 1][2];
      if (lastT > maxTime) maxTime = lastT;
    }
  }

  // precompute AGV task delivery times
  for (const agv of data.agvs) {
    agv._taskDeliveryTimes = computeTaskDeliveryTimes(agv, data.tasks);
  }

  progressBar.max = maxTime;
  progressBar.value = 0;
  timeMax.textContent = '/ ' + maxTime;

  // update scenario badge
  if (data.meta && data.meta.scenario_name) {
    scenarioBadge.textContent = data.meta.scenario_name;
    scenarioBadge.classList.remove('hidden');
  }

  updateMetrics();
  resizeCanvases();
  renderMap();
  renderChart();
  updateInfoPanel();

  stop();
}

/**
 * Figure out at which time step each task was delivered by this AGV.
 */
function computeTaskDeliveryTimes(agv, allTasks) {
  const result = {};
  const taskMap = {};
  for (const t of allTasks) taskMap[t.id] = t;

  for (const tid of agv.tasks) {
    const task = taskMap[tid];
    if (!task) continue;
    // find the first time step the AGV reaches the task position
    for (const [px, py, pt] of agv.path) {
      if (px === task.x && py === task.y) {
        result[tid] = pt;
        break;
      }
    }
  }
  return result;
}

// ========== Canvas Sizing ==========
function resizeCanvases() {
  const wrapper = document.getElementById('canvas-wrapper');
  const dpr = window.devicePixelRatio || 1;

  mapCanvas.width = wrapper.clientWidth * dpr;
  mapCanvas.height = wrapper.clientHeight * dpr;
  mapCanvas.style.width = wrapper.clientWidth + 'px';
  mapCanvas.style.height = wrapper.clientHeight + 'px';
  mapCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const chartWrapper = document.getElementById('chart-card');
  chartCanvas.width = chartWrapper.clientWidth * dpr;
  chartCanvas.height = 160 * dpr;
  chartCanvas.style.width = (chartWrapper.clientWidth) + 'px';
  chartCanvas.style.height = '160px';
  chartCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

window.addEventListener('resize', () => {
  resizeCanvases();
  if (data) {
    renderMap();
    renderChart();
  }
});

// ========== Map Rendering ==========
function getCellSize() {
  if (!data) return 20;
  const w = mapCanvas.clientWidth;
  const h = mapCanvas.clientHeight;
  const mapW = data.map.width;
  const mapH = data.map.height;
  const pad = 40;
  return Math.floor(Math.min((w - pad * 2) / mapW, (h - pad * 2) / mapH));
}

function getMapOrigin() {
  if (!data) return { x: 20, y: 20 };
  const cellSize = getCellSize();
  const totalW = data.map.width * cellSize;
  const totalH = data.map.height * cellSize;
  return {
    x: Math.floor((mapCanvas.clientWidth - totalW) / 2),
    y: Math.floor((mapCanvas.clientHeight - totalH) / 2),
  };
}

function renderMap() {
  if (!data) return;

  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const w = mapCanvas.clientWidth;
  const h = mapCanvas.clientHeight;
  const mapW = data.map.width;
  const mapH = data.map.height;

  // Clear
  mapCtx.fillStyle = '#12141f';
  mapCtx.fillRect(0, 0, w, h);

  // Grid lines
  mapCtx.strokeStyle = '#1e2035';
  mapCtx.lineWidth = 0.5;
  for (let x = 0; x <= mapW; x++) {
    mapCtx.beginPath();
    mapCtx.moveTo(origin.x + x * cellSize, origin.y);
    mapCtx.lineTo(origin.x + x * cellSize, origin.y + mapH * cellSize);
    mapCtx.stroke();
  }
  for (let y = 0; y <= mapH; y++) {
    mapCtx.beginPath();
    mapCtx.moveTo(origin.x, origin.y + y * cellSize);
    mapCtx.lineTo(origin.x + mapW * cellSize, origin.y + y * cellSize);
    mapCtx.stroke();
  }

  // Obstacles
  for (const [ox, oy] of data.map.obstacles) {
    const px = origin.x + ox * cellSize;
    const py = origin.y + oy * cellSize;
    mapCtx.fillStyle = '#283040';
    mapCtx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
    mapCtx.strokeStyle = '#3a4560';
    mapCtx.lineWidth = 0.5;
    mapCtx.strokeRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
  }

  // Start nodes (only those used by AGVs)
  const usedStarts = new Set();
  for (const agv of data.agvs) {
    usedStarts.add(agv.start_pos[0] + ',' + agv.start_pos[1]);
  }
  for (const [sx, sy] of data.map.start_nodes) {
    if (!usedStarts.has(sx + ',' + sy)) continue;
    const px = origin.x + sx * cellSize;
    const py = origin.y + sy * cellSize;
    mapCtx.fillStyle = 'rgba(34, 197, 94, 0.2)';
    mapCtx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
    mapCtx.strokeStyle = '#22c55e';
    mapCtx.lineWidth = 1;
    mapCtx.strokeRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
  }

  // Depot
  const [dx, dy] = data.map.depot;
  const dpx = origin.x + dx * cellSize;
  const dpy = origin.y + dy * cellSize;
  mapCtx.fillStyle = 'rgba(245, 158, 11, 0.25)';
  mapCtx.fillRect(dpx + 1, dpy + 1, cellSize - 2, cellSize - 2);
  mapCtx.strokeStyle = '#f59e0b';
  mapCtx.lineWidth = 1.5;
  mapCtx.strokeRect(dpx + 1, dpy + 1, cellSize - 2, cellSize - 2);
  mapCtx.fillStyle = '#f59e0b';
  mapCtx.font = `bold ${Math.max(8, cellSize * 0.35)}px ${getComputedStyle(document.body).getPropertyValue('--font-sans')}`;
  mapCtx.textAlign = 'center';
  mapCtx.textBaseline = 'middle';
  mapCtx.fillText('D', dpx + cellSize / 2, dpy + cellSize / 2);

  // Tasks
  for (const task of data.tasks) {
    const px = origin.x + task.x * cellSize + cellSize / 2;
    const py = origin.y + task.y * cellSize + cellSize / 2;
    const r = Math.max(3, cellSize * 0.22);

    // check if task is already delivered at currentTime
    let delivered = false;
    for (const agv of data.agvs) {
      if (agv._taskDeliveryTimes && agv._taskDeliveryTimes[task.id] !== undefined) {
        if (currentTime >= agv._taskDeliveryTimes[task.id]) {
          delivered = true;
          break;
        }
      }
    }

    if (delivered) {
      mapCtx.globalAlpha = 0.3;
    }

    mapCtx.beginPath();
    mapCtx.arc(px, py, r, 0, Math.PI * 2);
    mapCtx.fillStyle = '#6366f1';
    mapCtx.fill();

    // task ID label
    if (cellSize >= 18) {
      mapCtx.fillStyle = '#c7d0e8';
      mapCtx.font = `${Math.max(7, cellSize * 0.28)}px ${getComputedStyle(document.body).getPropertyValue('--font-mono')}`;
      mapCtx.textAlign = 'center';
      mapCtx.textBaseline = 'bottom';
      mapCtx.fillText(task.id, px, py - r - 2);
    }

    mapCtx.globalAlpha = 1;
  }

  // AGV trails and positions
  for (let ai = 0; ai < data.agvs.length; ai++) {
    const agv = data.agvs[ai];
    const color = AGV_COLORS[ai % AGV_COLORS.length];

    // Draw trail (path up to currentTime)
    const trailPoints = agv.path.filter(p => p[2] <= currentTime);
    if (trailPoints.length > 1) {
      mapCtx.beginPath();
      mapCtx.strokeStyle = color;
      mapCtx.globalAlpha = 0.3;
      mapCtx.lineWidth = Math.max(1.5, cellSize * 0.08);
      mapCtx.lineJoin = 'round';
      mapCtx.lineCap = 'round';
      for (let i = 0; i < trailPoints.length; i++) {
        const px = origin.x + trailPoints[i][0] * cellSize + cellSize / 2;
        const py = origin.y + trailPoints[i][1] * cellSize + cellSize / 2;
        if (i === 0) mapCtx.moveTo(px, py);
        else mapCtx.lineTo(px, py);
      }
      mapCtx.stroke();
      mapCtx.globalAlpha = 1;
    }

    // Draw current position
    const pos = getAgvPositionAtTime(agv, currentTime);
    if (pos) {
      const px = origin.x + pos[0] * cellSize + cellSize / 2;
      const py = origin.y + pos[1] * cellSize + cellSize / 2;
      const agvR = Math.max(4, cellSize * 0.3);

      // glow
      mapCtx.beginPath();
      mapCtx.arc(px, py, agvR + 3, 0, Math.PI * 2);
      mapCtx.fillStyle = color + '30';
      mapCtx.fill();

      // body
      mapCtx.beginPath();
      mapCtx.arc(px, py, agvR, 0, Math.PI * 2);
      mapCtx.fillStyle = color;
      mapCtx.fill();

      // label
      mapCtx.fillStyle = '#fff';
      mapCtx.font = `bold ${Math.max(7, cellSize * 0.28)}px ${getComputedStyle(document.body).getPropertyValue('--font-sans')}`;
      mapCtx.textAlign = 'center';
      mapCtx.textBaseline = 'middle';
      mapCtx.fillText(agv.id, px, py);
    }
  }

  // Axis labels
  mapCtx.fillStyle = '#4a5070';
  mapCtx.font = `${Math.max(7, cellSize * 0.3)}px ${getComputedStyle(document.body).getPropertyValue('--font-mono')}`;
  mapCtx.textAlign = 'center';
  mapCtx.textBaseline = 'top';
  for (let x = 0; x < mapW; x += Math.max(1, Math.floor(mapW / 10))) {
    mapCtx.fillText(x, origin.x + x * cellSize + cellSize / 2, origin.y + mapH * cellSize + 4);
  }
  mapCtx.textAlign = 'right';
  mapCtx.textBaseline = 'middle';
  for (let y = 0; y < mapH; y += Math.max(1, Math.floor(mapH / 10))) {
    mapCtx.fillText(y, origin.x - 5, origin.y + y * cellSize + cellSize / 2);
  }
}

function getAgvPositionAtTime(agv, t) {
  if (!agv.path || agv.path.length === 0) {
    // no path — show at start position
    return [agv.start_pos[0], agv.start_pos[1], t];
  }
  // if t is before the first path point, show at start position
  if (t < agv.path[0][2]) {
    return [agv.start_pos[0], agv.start_pos[1], t];
  }
  // find exact match or last position before t
  let best = null;
  for (const p of agv.path) {
    if (p[2] <= t) best = p;
    if (p[2] === t) return p;
  }
  return best;
}

// ========== Tooltip ==========
mapCanvas.addEventListener('mousemove', (e) => {
  if (!data) return;
  const rect = mapCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const cellSize = getCellSize();
  const origin = getMapOrigin();
  const gx = Math.floor((mx - origin.x) / cellSize);
  const gy = Math.floor((my - origin.y) / cellSize);

  if (gx < 0 || gy < 0 || gx >= data.map.width || gy >= data.map.height) {
    mapTooltip.classList.add('hidden');
    return;
  }

  let info = `(${gx}, ${gy})`;

  // check obstacles
  const isObstacle = data.map.obstacles.some(o => o[0] === gx && o[1] === gy);
  if (isObstacle) info += ' — 障碍物';

  // check tasks
  const task = data.tasks.find(t => t.x === gx && t.y === gy);
  if (task) info += ` — 任务${task.id} [W=${task.weight}kg, DD=${task.deadline}]`;

  // check AGVs
  for (let ai = 0; ai < data.agvs.length; ai++) {
    const pos = getAgvPositionAtTime(data.agvs[ai], currentTime);
    if (pos && pos[0] === gx && pos[1] === gy) {
      info += ` — AGV-${data.agvs[ai].id}`;
    }
  }

  mapTooltip.textContent = info;
  mapTooltip.style.left = (mx + 14) + 'px';
  mapTooltip.style.top = (my - 8) + 'px';
  mapTooltip.classList.remove('hidden');
});

mapCanvas.addEventListener('mouseleave', () => {
  mapTooltip.classList.add('hidden');
});

// ========== Playback Controls ==========
btnPlay.addEventListener('click', () => {
  if (isPlaying) stop();
  else play();
});

btnStepFwd.addEventListener('click', () => {
  stop();
  stepForward();
});

btnStepBack.addEventListener('click', () => {
  stop();
  stepBackward();
});

btnReset.addEventListener('click', () => {
  stop();
  currentTime = 0;
  progressBar.value = 0;
  updateTimeDisplay();
  renderMap();
  updateInfoPanel();
});

speedSelect.addEventListener('change', () => {
  playSpeed = parseInt(speedSelect.value);
  if (isPlaying) {
    clearInterval(playInterval);
    playInterval = setInterval(tick, playSpeed);
  }
});

progressBar.addEventListener('input', () => {
  currentTime = parseInt(progressBar.value);
  updateTimeDisplay();
  renderMap();
  updateInfoPanel();
});

function play() {
  if (!data) return;
  isPlaying = true;
  btnPlay.textContent = '⏸';
  playInterval = setInterval(tick, playSpeed);
}

function stop() {
  isPlaying = false;
  btnPlay.textContent = '▶';
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
  if (!data || currentTime >= maxTime) return;
  currentTime++;
  progressBar.value = currentTime;
  updateTimeDisplay();
  renderMap();
  updateInfoPanel();
}

function stepBackward() {
  if (!data || currentTime <= 0) return;
  currentTime--;
  progressBar.value = currentTime;
  updateTimeDisplay();
  renderMap();
  updateInfoPanel();
}

function updateTimeDisplay() {
  timeDisplay.textContent = 't = ' + currentTime;
}

// ========== Info Panel ==========
function updateMetrics() {
  if (!data) return;
  const f = data.fitness;
  document.getElementById('m-F').textContent = f.F;
  document.getElementById('m-N').textContent = f.N;
  document.getElementById('m-D').textContent = f.D;
  document.getElementById('m-T').textContent = f.T;
  document.getElementById('m-conflict').textContent = f.conflict_count;
  document.getElementById('m-replan').textContent = f.replan_count;
}

function updateInfoPanel() {
  if (!data) return;
  const tbody = document.getElementById('agv-table-body');
  tbody.innerHTML = '';

  for (let ai = 0; ai < data.agvs.length; ai++) {
    const agv = data.agvs[ai];
    const color = AGV_COLORS[ai % AGV_COLORS.length];
    const pos = getAgvPositionAtTime(agv, currentTime);

    // compute completed tasks
    let completedTasks = 0;
    if (agv._taskDeliveryTimes) {
      for (const tid of agv.tasks) {
        if (agv._taskDeliveryTimes[tid] !== undefined && currentTime >= agv._taskDeliveryTimes[tid]) {
          completedTasks++;
        }
      }
    }

    // determine status
    let status, statusClass;
    if (!pos || currentTime === 0) {
      status = '待命';
      statusClass = 'idle';
    } else if (currentTime >= agv.finish_time) {
      status = '完成';
      statusClass = 'done';
    } else {
      // check if at a task position (serving)
      const taskMap = {};
      for (const t of data.tasks) taskMap[t.id] = t;
      let isServing = false;
      for (const tid of agv.tasks) {
        const task = taskMap[tid];
        if (task && pos[0] === task.x && pos[1] === task.y) {
          isServing = true;
          break;
        }
      }
      status = isServing ? '服务中' : '行驶中';
      statusClass = isServing ? 'serving' : 'moving';
    }

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="agv-color-dot" style="background:${color}"></span>${agv.id}</td>
      <td>${pos ? `(${pos[0]},${pos[1]})` : '—'}</td>
      <td>${completedTasks}/${agv.tasks.length}</td>
      <td>${agv.load}kg</td>
      <td><span class="status-tag ${statusClass}">${status}</span></td>
    `;
    tbody.appendChild(tr);
  }
}

// ========== Convergence Chart ==========
function renderChart() {
  if (!data || !data.convergence || data.convergence.length === 0) {
    chartCtx.clearRect(0, 0, chartCanvas.clientWidth, 160);
    chartCtx.fillStyle = '#4a5070';
    chartCtx.font = '12px Inter, sans-serif';
    chartCtx.textAlign = 'center';
    chartCtx.fillText('暂无收敛数据', chartCanvas.clientWidth / 2, 80);
    return;
  }

  const conv = data.convergence;
  const w = chartCanvas.clientWidth;
  const h = 160;
  const pad = { top: 20, right: 16, bottom: 28, left: 50 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;

  chartCtx.clearRect(0, 0, w, h);

  // compute range
  const fValues = conv.map(c => c.best_fitness);
  const fMin = Math.min(...fValues);
  const fMax = Math.max(...fValues);
  const fRange = fMax - fMin || 1;
  const iterMax = conv.length;

  // background
  chartCtx.fillStyle = '#161822';
  chartCtx.fillRect(0, 0, w, h);

  // grid lines
  chartCtx.strokeStyle = '#1e2035';
  chartCtx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const yy = pad.top + (plotH / 4) * i;
    chartCtx.beginPath();
    chartCtx.moveTo(pad.left, yy);
    chartCtx.lineTo(pad.left + plotW, yy);
    chartCtx.stroke();

    // y labels
    const val = fMax - (fRange / 4) * i;
    chartCtx.fillStyle = '#4a5070';
    chartCtx.font = '9px JetBrains Mono, monospace';
    chartCtx.textAlign = 'right';
    chartCtx.textBaseline = 'middle';
    chartCtx.fillText(Math.round(val), pad.left - 6, yy);
  }

  // x labels
  chartCtx.textAlign = 'center';
  chartCtx.textBaseline = 'top';
  const xStep = Math.max(1, Math.floor(iterMax / 5));
  for (let i = 0; i < iterMax; i += xStep) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    chartCtx.fillText(conv[i].iter, xx, pad.top + plotH + 6);
  }
  // always label last
  chartCtx.fillText(conv[iterMax - 1].iter, pad.left + plotW, pad.top + plotH + 6);

  // axis labels
  chartCtx.fillStyle = '#636882';
  chartCtx.font = '9px Inter, sans-serif';
  chartCtx.save();
  chartCtx.translate(12, pad.top + plotH / 2);
  chartCtx.rotate(-Math.PI / 2);
  chartCtx.textAlign = 'center';
  chartCtx.fillText('F', 0, 0);
  chartCtx.restore();

  chartCtx.textAlign = 'center';
  chartCtx.fillText('迭代', pad.left + plotW / 2, h - 4);

  // gradient fill under curve
  const gradient = chartCtx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
  gradient.addColorStop(0, 'rgba(99, 102, 241, 0.25)');
  gradient.addColorStop(1, 'rgba(99, 102, 241, 0.02)');

  chartCtx.beginPath();
  for (let i = 0; i < conv.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    const yy = pad.top + plotH - ((conv[i].best_fitness - fMin) / fRange) * plotH;
    if (i === 0) chartCtx.moveTo(xx, yy);
    else chartCtx.lineTo(xx, yy);
  }
  chartCtx.lineTo(pad.left + plotW, pad.top + plotH);
  chartCtx.lineTo(pad.left, pad.top + plotH);
  chartCtx.closePath();
  chartCtx.fillStyle = gradient;
  chartCtx.fill();

  // line
  chartCtx.beginPath();
  for (let i = 0; i < conv.length; i++) {
    const xx = pad.left + (i / (iterMax - 1 || 1)) * plotW;
    const yy = pad.top + plotH - ((conv[i].best_fitness - fMin) / fRange) * plotH;
    if (i === 0) chartCtx.moveTo(xx, yy);
    else chartCtx.lineTo(xx, yy);
  }
  chartCtx.strokeStyle = '#6366f1';
  chartCtx.lineWidth = 2;
  chartCtx.lineJoin = 'round';
  chartCtx.stroke();

  // final value dot
  const lastConv = conv[conv.length - 1];
  const lastX = pad.left + plotW;
  const lastY = pad.top + plotH - ((lastConv.best_fitness - fMin) / fRange) * plotH;
  chartCtx.beginPath();
  chartCtx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
  chartCtx.fillStyle = '#06b6d4';
  chartCtx.fill();

  chartCtx.fillStyle = '#06b6d4';
  chartCtx.font = 'bold 10px JetBrains Mono, monospace';
  chartCtx.textAlign = 'right';
  chartCtx.textBaseline = 'bottom';
  chartCtx.fillText(lastConv.best_fitness, lastX - 6, lastY - 5);
}

// ========== Init ==========
resizeCanvases();
