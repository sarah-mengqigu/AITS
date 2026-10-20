import client from './client'

const BASE = '/performance'

/** 性能测试模块（/api/performance/）。 */
export const performanceApi = {
  // 负载配置
  listConfigs(params = {}) {
    return client.get(`${BASE}/configs/`, { params }).then((response) => response.data)
  },
  retrieveConfig(id) {
    return client.get(`${BASE}/configs/${id}/`).then((response) => response.data)
  },
  createConfig(data) {
    return client.post(`${BASE}/configs/`, data).then((response) => response.data)
  },
  updateConfig(id, data) {
    return client.patch(`${BASE}/configs/${id}/`, data).then((response) => response.data)
  },
  removeConfig(id) {
    return client.delete(`${BASE}/configs/${id}/`).then((response) => response.data)
  },

  // 场景
  listScenarios(params = {}) {
    return client.get(`${BASE}/scenarios/`, { params }).then((response) => response.data)
  },
  retrieveScenario(id) {
    return client.get(`${BASE}/scenarios/${id}/`).then((response) => response.data)
  },
  createScenario(data) {
    return client.post(`${BASE}/scenarios/`, data).then((response) => response.data)
  },
  updateScenario(id, data) {
    return client.patch(`${BASE}/scenarios/${id}/`, data).then((response) => response.data)
  },
  removeScenario(id) {
    return client.delete(`${BASE}/scenarios/${id}/`).then((response) => response.data)
  },
  generateScript(id) {
    return client.post(`${BASE}/scenarios/${id}/generate_script/`).then((response) => response.data)
  },
  runScenario(id, data = {}) {
    return client.post(`${BASE}/scenarios/${id}/run/`, data).then((response) => response.data)
  },

  // 执行
  listExecutions(params = {}) {
    return client.get(`${BASE}/executions/`, { params }).then((response) => response.data)
  },
  retrieveExecution(id) {
    return client.get(`${BASE}/executions/${id}/`).then((response) => response.data)
  },
  cancelExecution(id, data = {}) {
    return client.post(`${BASE}/executions/${id}/cancel/`, data).then((response) => response.data)
  },
  /**
   * 执行报告 JSON。
   *
   * 后端当前始终返回 JSON（会忽略 `download` 参数），这里仍把 params
   * 透传出去，便于后端后续支持 `?download=1` 时无需修改调用方。
   */
  executionReport(id, params = {}) {
    return client.get(`${BASE}/executions/${id}/report/`, { params }).then((response) => response.data)
  },
  /** 下载报告：Blob + JWT 拉取，兼容 JSON 与文件流两种响应。 */
  downloadExecutionReport(id) {
    return client.get(`${BASE}/executions/${id}/report/`, {
      params: { download: 1 },
      responseType: 'blob',
      timeout: 120000,
    })
  },

  // Grafana Webhook（后端免 JWT，这里保留方法供调试；必须 skipAuth）
  grafanaWebhook(payload) {
    return client
      .post(`${BASE}/grafana/webhook/`, payload, { skipAuth: true })
      .then((response) => response.data)
  },

  // AI 诊断
  listDiagnoses(params = {}) {
    return client.get(`${BASE}/diagnoses/`, { params }).then((response) => response.data)
  },
  retrieveDiagnosis(id) {
    return client.get(`${BASE}/diagnoses/${id}/`).then((response) => response.data)
  },
  updateDiagnosis(id, data) {
    return client.patch(`${BASE}/diagnoses/${id}/`, data).then((response) => response.data)
  },

  // 大盘聚合
  dashboard(params = {}) {
    return client.get(`${BASE}/dashboard/`, { params }).then((response) => response.data)
  },
}

export default performanceApi
