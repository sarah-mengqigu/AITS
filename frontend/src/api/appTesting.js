import client from './client'

const BASE = '/app-testing'

/** App 测试模块（/api/app-testing/）。 */
export const appTestingApi = {
  // 模块
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

  // 应用
  listApplications(params = {}) {
    return client.get(`${BASE}/applications/`, { params }).then((response) => response.data)
  },
  retrieveApplication(id) {
    return client.get(`${BASE}/applications/${id}/`).then((response) => response.data)
  },
  createApplication(data) {
    return client.post(`${BASE}/applications/`, data).then((response) => response.data)
  },
  updateApplication(id, data) {
    return client.patch(`${BASE}/applications/${id}/`, data).then((response) => response.data)
  },
  removeApplication(id) {
    return client.delete(`${BASE}/applications/${id}/`).then((response) => response.data)
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
  generateSteps(caseId, data = {}) {
    return client.post(`${BASE}/cases/${caseId}/generate_steps/`, data).then((response) => response.data)
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

  // 运行记录
  listRuns(params = {}) {
    return client.get(`${BASE}/runs/`, { params }).then((response) => response.data)
  },
  retrieveRun(id) {
    return client.get(`${BASE}/runs/${id}/`).then((response) => response.data)
  },
  cancelRun(id) {
    return client.post(`${BASE}/runs/${id}/cancel/`).then((response) => response.data)
  },
  runReport(id, params = {}) {
    return client.get(`${BASE}/runs/${id}/report/`, { params }).then((response) => response.data)
  },
  /** 报告下载（`?download=1` 返回 JSON 文件流）。 */
  downloadRunReport(id) {
    return client.get(`${BASE}/runs/${id}/report/`, {
      params: { download: 1 },
      responseType: 'blob',
    })
  },

  // 设备（Sonic 代理，未配置时返回空数组 + warning）
  listDevices(params = {}) {
    return client.get(`${BASE}/devices/`, { params }).then((response) => response.data)
  },
  retrieveDevice(udid, params = {}) {
    return client.get(`${BASE}/devices/${udid}/`, { params }).then((response) => response.data)
  },
  deviceRemote(udid, data = {}) {
    return client.post(`${BASE}/devices/${udid}/remote/`, data).then((response) => response.data)
  },
  listElementPages(params = {}) {
    return client.get(`${BASE}/element-pages/`, { params }).then((response) => response.data)
  },
}

export default appTestingApi
