import client from './client'

const BASE = '/api-testing'

/** API 测试模块（/api/api-testing/）。 */
export const apiTestingApi = {
  // 接口规范
  listSpecs(params = {}) {
    return client.get(`${BASE}/specs/`, { params }).then((response) => response.data)
  },
  retrieveSpec(id) {
    return client.get(`${BASE}/specs/${id}/`).then((response) => response.data)
  },
  createSpec(data) {
    return client.post(`${BASE}/specs/`, data).then((response) => response.data)
  },
  updateSpec(id, data) {
    return client.patch(`${BASE}/specs/${id}/`, data).then((response) => response.data)
  },
  removeSpec(id) {
    return client.delete(`${BASE}/specs/${id}/`).then((response) => response.data)
  },
  /** 导入规范：form 可含 project / file / content / format / base_url。 */
  importSpec(payload = {}) {
    if (payload.file) {
      const form = new FormData()
      Object.entries(payload).forEach(([key, value]) => {
        if (value !== undefined && value !== null && key !== 'file') form.append(key, value)
      })
      form.append('file', payload.file)
      return client
        .post(`${BASE}/specs/import/`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((response) => response.data)
    }
    return client.post(`${BASE}/specs/import/`, payload).then((response) => response.data)
  },
  reparseSpec(id) {
    return client.post(`${BASE}/specs/${id}/reparse/`).then((response) => response.data)
  },

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

  // 端点
  listEndpoints(params = {}) {
    return client.get(`${BASE}/endpoints/`, { params }).then((response) => response.data)
  },
  retrieveEndpoint(id) {
    return client.get(`${BASE}/endpoints/${id}/`).then((response) => response.data)
  },
  createEndpoint(data) {
    return client.post(`${BASE}/endpoints/`, data).then((response) => response.data)
  },
  updateEndpoint(id, data) {
    return client.patch(`${BASE}/endpoints/${id}/`, data).then((response) => response.data)
  },
  removeEndpoint(id) {
    return client.delete(`${BASE}/endpoints/${id}/`).then((response) => response.data)
  },
  generateCases(endpointId, data = {}) {
    return client
      .post(`${BASE}/endpoints/${endpointId}/generate_cases/`, data)
      .then((response) => response.data)
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
  generateScript(caseId) {
    return client.post(`${BASE}/cases/${caseId}/generate_script/`).then((response) => response.data)
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
  cancelExecution(id, data = {}) {
    return client.post(`${BASE}/executions/${id}/cancel/`, data).then((response) => response.data)
  },
  executionReport(id) {
    return client.get(`${BASE}/executions/${id}/report/`).then((response) => response.data)
  },

  // Postman Collection 导入（multipart: project / file / name / base_url）
  importPostman(projectId, file, extra = {}) {
    const form = new FormData()
    form.append('project', projectId)
    form.append('file', file)
    Object.entries(extra).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') form.append(key, value)
    })
    return client
      .post(`${BASE}/postman/import/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((response) => response.data)
  },

  // AI 场景生成（body: project / requirement / save）
  generateScenario(projectId, requirement, { save = true } = {}) {
    return client
      .post(`${BASE}/ai/generate_scenario/`, {
        project: projectId,
        requirement,
        save,
      })
      .then((response) => response.data)
  },
}

export default apiTestingApi
