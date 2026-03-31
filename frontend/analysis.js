(function (globalScope) {
  function buildTaskMap(tasks) {
    const taskMap = {};
    for (const task of tasks || []) {
      taskMap[task.id] = task;
    }
    return taskMap;
  }

  function computeTaskDeliveryTimes(agv, allTasks) {
    const result = {};
    const taskMap = buildTaskMap(allTasks);

    for (const taskId of agv.tasks || []) {
      const task = taskMap[taskId];
      if (!task) {
        continue;
      }
      for (const [px, py, pt] of agv.path || []) {
        if (px === task.x && py === task.y) {
          result[taskId] = pt;
          break;
        }
      }
    }
    return result;
  }

  function getPathPositionAtTime(agv, timeStep) {
    if (!agv.path || agv.path.length === 0) {
      return [agv.start_pos[0], agv.start_pos[1], timeStep];
    }
    if (timeStep < agv.path[0][2]) {
      return [agv.start_pos[0], agv.start_pos[1], timeStep];
    }

    let best = null;
    for (const point of agv.path) {
      if (point[2] <= timeStep) {
        best = point;
      }
      if (point[2] === timeStep) {
        return point;
      }
    }
    return best;
  }

  function getAgvCurrentTarget(agv, allTasks, deliveryTimes, timeStep, depot) {
    const targetDepot = Array.isArray(depot) ? depot : [0, 0];
    const taskMap = buildTaskMap(allTasks);
    for (const taskId of agv.tasks || []) {
      const deliveryTime = deliveryTimes[taskId];
      if (deliveryTime === undefined || timeStep < deliveryTime) {
        const task = taskMap[taskId];
        if (!task) {
          continue;
        }
        return {
          type: "task",
          taskId,
          label: `任务 ${taskId}`,
          x: task.x,
          y: task.y,
        };
      }
    }

    return {
      type: "depot",
      label: "返回终点",
      x: targetDepot[0],
      y: targetDepot[1],
    };
  }

  function buildTaskAssignments(data) {
    const taskOwners = {};

    for (const agv of data.agvs || []) {
      for (const taskId of agv.tasks || []) {
        taskOwners[taskId] = agv.id;
      }
    }

    return taskOwners;
  }

  function summarizeAtTime(data, timeStep) {
    const taskOwners = buildTaskAssignments(data);
    const completedTaskIds = new Set();
    let activeAgvCount = 0;
    let completedAgvCount = 0;

    for (const agv of data.agvs || []) {
      const deliveryTimes = agv._taskDeliveryTimes || computeTaskDeliveryTimes(agv, data.tasks || []);
      for (const taskId of agv.tasks || []) {
        if (deliveryTimes[taskId] !== undefined && timeStep >= deliveryTimes[taskId]) {
          completedTaskIds.add(taskId);
        }
      }

      if (agv.finish_time !== undefined && timeStep >= agv.finish_time) {
        completedAgvCount += 1;
      } else if ((agv.path || []).length > 0 && timeStep >= agv.path[0][2]) {
        activeAgvCount += 1;
      }
    }

    const totalTasks = (data.tasks || []).length;
    const completedTasks = completedTaskIds.size;
    const completionRate = totalTasks === 0 ? 0 : Math.round((completedTasks / totalTasks) * 100);

    return {
      totalTasks,
      completedTasks,
      completionRate,
      activeAgvCount,
      completedAgvCount,
      taskOwners,
    };
  }

  function buildEventTimeline(data) {
    const events = [];
    const taskMap = buildTaskMap(data.tasks || []);
    const typeOrder = {
      task_complete: 0,
      agv_complete: 1,
    };

    for (const agv of data.agvs || []) {
      const deliveryTimes = agv._taskDeliveryTimes || computeTaskDeliveryTimes(agv, data.tasks || []);
      for (const taskId of agv.tasks || []) {
        const task = taskMap[taskId];
        const deliveryTime = deliveryTimes[taskId];
        if (task && deliveryTime !== undefined) {
          events.push({
            time: deliveryTime,
            type: "task_complete",
            agvId: agv.id,
            taskId,
            label: `AGV-${agv.id} 完成任务 ${taskId}`,
            detail: `坐标 (${task.x}, ${task.y})，截止时间 ${task.deadline}`,
          });
        }
      }

      if (agv.finish_time !== undefined) {
        events.push({
          time: agv.finish_time,
          type: "agv_complete",
          agvId: agv.id,
          label: `AGV-${agv.id} 完成全部任务`,
          detail: `总任务数 ${agv.tasks.length}，总载重 ${agv.load}kg`,
        });
      }
    }

    events.sort((a, b) => {
      if (a.time !== b.time) {
        return a.time - b.time;
      }
      if (a.type !== b.type) {
        return (typeOrder[a.type] ?? 99) - (typeOrder[b.type] ?? 99);
      }
      return a.agvId - b.agvId;
    });

    return events;
  }

  const api = {
    buildTaskMap,
    buildTaskAssignments,
    computeTaskDeliveryTimes,
    getPathPositionAtTime,
    getAgvCurrentTarget,
    summarizeAtTime,
    buildEventTimeline,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  globalScope.AnalysisUtils = api;
})(typeof window !== "undefined" ? window : globalThis);
