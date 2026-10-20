import client from './client'

const BASE = '/scheduled-tasks'

/** 定时任务（/api/scheduled-tasks/）。 */
export const scheduledTasksApi = {
  listTasks(params = {}) {
    return client.get(`${BASE}/tasks/`, { params }).then((response) => response.data)
  },
  retrieveTask(id) {
    return client.get(`${BASE}/tasks/${id}/`).then((response) => response.data)
  },
  createTask(data) {
    return client.post(`${BASE}/tasks/`, data).then((response) => response.data)
  },
  updateTask(id, data) {
    return client.patch(`${BASE}/tasks/${id}/`, data).then((response) => response.data)
  },
  removeTask(id) {
    return client.delete(`${BASE}/tasks/${id}/`).then((response) => response.data)
  },
  runTask(id) {
    return client.post(`${BASE}/tasks/${id}/run/`).then((response) => response.data)
  },
  toggleTask(id) {
    return client.post(`${BASE}/tasks/${id}/toggle/`).then((response) => response.data)
  },
  taskLogs(id, params = {}) {
    return client.get(`${BASE}/tasks/${id}/logs/`, { params }).then((response) => response.data)
  },

  listLogs(params = {}) {
    return client.get(`${BASE}/logs/`, { params }).then((response) => response.data)
  },
  retrieveLog(id) {
    return client.get(`${BASE}/logs/${id}/`).then((response) => response.data)
  },

  cronPreview(expr, params = {}) {
    return client
      .get(`${BASE}/cron/preview/`, { params: { count: 5, ...params, expr } })
      .then((response) => response.data)
  },
}

export default scheduledTasksApi
