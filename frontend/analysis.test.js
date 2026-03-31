const assert = require("node:assert/strict");

const {
  computeTaskDeliveryTimes,
  getAgvCurrentTarget,
  summarizeAtTime,
  buildEventTimeline,
  buildTaskAssignments,
} = require("./analysis.js");


function runTest(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}


const sampleTasks = [
  { id: 1, x: 2, y: 2, weight: 20, deadline: 10 },
  { id: 2, x: 4, y: 4, weight: 15, deadline: 20 },
];

const sampleAgvs = [
  {
    id: 0,
    start_pos: [0, 0],
    tasks: [1, 2],
    load: 35,
    finish_time: 13,
    path: [
      [0, 0, 0],
      [1, 0, 1],
      [2, 0, 2],
      [2, 1, 3],
      [2, 2, 4],
      [3, 2, 7],
      [4, 2, 8],
      [4, 3, 9],
      [4, 4, 10],
      [5, 4, 11],
      [5, 5, 12],
      [6, 5, 13],
    ],
  },
  {
    id: 1,
    start_pos: [0, 1],
    tasks: [2],
    load: 15,
    finish_time: 6,
    path: [
      [0, 1, 0],
      [1, 1, 1],
      [2, 1, 2],
      [3, 1, 3],
      [4, 1, 4],
      [4, 2, 5],
      [4, 4, 6],
    ],
  },
];

const sampleData = {
  tasks: sampleTasks,
  agvs: sampleAgvs,
  map: {
    depot: [6, 6],
  },
};

runTest("computeTaskDeliveryTimes returns the first arrival time for each task", () => {
  const deliveryTimes = computeTaskDeliveryTimes(sampleAgvs[0], sampleTasks);
  assert.deepEqual(deliveryTimes, { 1: 4, 2: 10 });
});

runTest("getAgvCurrentTarget returns the next unfinished task and then depot", () => {
  const deliveryTimes = computeTaskDeliveryTimes(sampleAgvs[0], sampleTasks);

  assert.equal(getAgvCurrentTarget(sampleAgvs[0], sampleTasks, deliveryTimes, 0).label, "任务 1");
  assert.equal(getAgvCurrentTarget(sampleAgvs[0], sampleTasks, deliveryTimes, 5).label, "任务 2");
  assert.equal(getAgvCurrentTarget(sampleAgvs[0], sampleTasks, deliveryTimes, 11).label, "返回终点");
});

runTest("summarizeAtTime reports completed tasks and active AGVs for a time step", () => {
  const summary = summarizeAtTime(sampleData, 5);

  assert.equal(summary.totalTasks, 2);
  assert.equal(summary.completedTasks, 1);
  assert.equal(summary.activeAgvCount, 2);
  assert.equal(summary.completedAgvCount, 0);
  assert.equal(summary.completionRate, 50);
});

runTest("buildEventTimeline creates sorted task and AGV completion events", () => {
  const events = buildEventTimeline(sampleData);

  assert.deepEqual(
    events.map((event) => [event.time, event.type, event.agvId, event.taskId ?? null]),
    [
      [4, "task_complete", 0, 1],
      [6, "task_complete", 1, 2],
      [6, "agv_complete", 1, null],
      [10, "task_complete", 0, 2],
      [13, "agv_complete", 0, null],
    ],
  );
});

runTest("buildTaskAssignments maps each task to its owning AGV", () => {
  const assignments = buildTaskAssignments({
    tasks: [
      { id: 11, x: 1, y: 1 },
      { id: 12, x: 2, y: 2 },
      { id: 13, x: 3, y: 3 },
    ],
    agvs: [
      { id: 3, tasks: [11, 13] },
      { id: 7, tasks: [12] },
    ],
  });

  assert.deepEqual(assignments, { 11: 3, 12: 7, 13: 3 });
});

console.log("All frontend analysis tests passed.");
