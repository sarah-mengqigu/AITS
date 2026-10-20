import client from './client'

const BASE = '/web-testing'

/** Web UI 测试模块（/api/web-testing/）。 */
export const webTestingApi = {
  // 模块树
  listModules(params = {}) {
    return client.get(`${BASE}/modules/`, { params }).then((response) => response.data)
  },
  moduleTree(params = {}) {
    return client.get(`${BASE}/modules/tree/`, { params }).then((response) => response.data)
  },
  createModule(data) {
    return client.post(`${BASE}/modules/`, data).then((response) => response.data)
  },
  updateModule(id, data) {
    return client.patch(`${BASE}/modules/${id}/`, data).then((response) => response.data)
  },
  removeModule(id) {
    return client.delete(`${BASE}/modules/${id}/`).then((response) => response.data)
  },

  // 用例
  listCases(params = {}) {
    return client.get(`${BASE}/cases/`, { params }).then((response) => response.data)
  },
  retrieveCase(id) {
    return client.get(`${BASE}/cases/${id}/`).then((response) => response.data)
  },
  createCase(data) {
    return client.post(`${BASE}/cases/`, data).then((response) => response.data)
  },
  updateCase(id, data) {
    return client.patch(`${BASE}/cases/${id}/`, data).then((response) => response.data)
  },
  removeCase(id) {
    return client.delete(`${BASE}/cases/${id}/`).then((response) => response.data)
  },
  generateScript(caseId, data = {}) {
    return client
      .post(`${BASE}/cases/${caseId}/generate_script/`, data)
      .then((response) => response.data)
  },
  generateFromNl(caseId, data = {}) {
    return client
      .post(`${BASE}/cases/${caseId}/generate_from_nl/`, data)
      .then((response) => response.data)
  },
  runCase(caseId, data = {}) {
    return client.post(`${BASE}/cases/${caseId}/run/`, data).then((response) => response.data)
  },

  // 套件
  listSuites(params = {}) {
    return client.get(`${BASE}/suites/`, { params }).then((response) => response.data)
  },
  retrieveSuite(id) {
    return client.get(`${BASE}/suites/${id}/`).then((response) => response.data)
  },
  createSuite(data) {
    return client.post(`${BASE}/suites/`, data).then((response) => response.data)
  },
  updateSuite(id, data) {
    return client.patch(`${BASE}/suites/${id}/`, data).then((response) => response.data)
  },
  removeSuite(id) {
    return client.delete(`${BASE}/suites/${id}/`).then((response) => response.data)
  },
  runSuite(id, data = {}) {
    return client.post(`${BASE}/suites/${id}/run/`, data).then((response) => response.data)
  },

  // 执行
  listExecutions(params = {}) {
    return client.get(`${BASE}/executions/`, { params }).then((response) => response.data)
  },
  retrieveExecution(id) {
    return client.get(`${BASE}/executions/${id}/`).then((response) => response.data)
  },
  cancelExecution(id) {
    return client.post(`${BASE}/executions/${id}/cancel/`).then((response) => response.data)
  },
  executionReport(id, params = {}) {
    return client
      .get(`${BASE}/executions/${id}/report/`, { params })
      .then((response) => response.data)
  },
  /** 报告下载（`?download=1` 返回 HTML 文件流）。 */
  downloadExecutionReport(id) {
    return client.get(`${BASE}/executions/${id}/report/`, {
      params: { download: 1 },
      responseType: 'blob',
    })
  },

  // POM：页面 / 元素
  listPages(params = {}) {
    return client.get(`${BASE}/pages/`, { params }).then((response) => response.data)
  },
  createPage(data) {
    return client.post(`${BASE}/pages/`, data).then((response) => response.data)
  },
  updatePage(id, data) {
    return client.patch(`${BASE}/pages/${id}/`, data).then((response) => response.data)
  },
  removePage(id) {
    return client.delete(`${BASE}/pages/${id}/`).then((response) => response.data)
  },
  listElements(params = {}) {
    return client.get(`${BASE}/elements/`, { params }).then((response) => response.data)
  },
  createElement(data) {
    return client.post(`${BASE}/elements/`, data).then((response) => response.data)
  },
  updateElement(id, data) {
    return client.patch(`${BASE}/elements/${id}/`, data).then((response) => response.data)
  },
  removeElement(id) {
    return client.delete(`${BASE}/elements/${id}/`).then((response) => response.data)
  },
  /** `GET /api/web-testing/pages/{pageId}/elements/`（不分页，列表过滤的兜底）。 */
  pageElements(pageId, params = {}) {
    return client
      .get(`${BASE}/pages/${pageId}/elements/`, { params })
      .then((response) => response.data)
  },
  /** 批量 upsert：`POST /api/web-testing/elements/bulk/`。 */
  bulkUpsertElements(data) {
    return client.post(`${BASE}/elements/bulk/`, data).then((response) => response.data)
  },

  // MidScene 脚本
  listMidsceneScripts(params = {}) {
    return client.get(`${BASE}/midscene-scripts/`, { params }).then((response) => response.data)
  },
  retrieveMidsceneScript(id) {
    return client.get(`${BASE}/midscene-scripts/${id}/`).then((response) => response.data)
  },
  createMidsceneScript(data) {
    return client.post(`${BASE}/midscene-scripts/`, data).then((response) => response.data)
  },
  updateMidsceneScript(id, data) {
    return client.patch(`${BASE}/midscene-scripts/${id}/`, data).then((response) => response.data)
  },
  removeMidsceneScript(id) {
    return client.delete(`${BASE}/midscene-scripts/${id}/`).then((response) => response.data)
  },
  generateMidsceneScript(id, data = {}) {
    return client
      .post(`${BASE}/midscene-scripts/${id}/generate/`, data)
      .then((response) => response.data)
  },
}

export default webTestingApi
