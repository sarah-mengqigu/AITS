import client from './client'

const BASE = '/ai'

/** AI 中心（/api/ai/）。 */
export const aiCoreApi = {
  // LLM 配置
  listLlmConfigs(params = {}) {
    return client.get(`${BASE}/llm-configs/`, { params }).then((response) => response.data)
  },
  retrieveLlmConfig(id) {
    return client.get(`${BASE}/llm-configs/${id}/`).then((response) => response.data)
  },
  createLlmConfig(data) {
    return client.post(`${BASE}/llm-configs/`, data).then((response) => response.data)
  },
  updateLlmConfig(id, data) {
    return client.patch(`${BASE}/llm-configs/${id}/`, data).then((response) => response.data)
  },
  removeLlmConfig(id) {
    return client.delete(`${BASE}/llm-configs/${id}/`).then((response) => response.data)
  },
  testLlmConfig(id, data = {}) {
    return client.post(`${BASE}/llm-configs/${id}/test/`, data).then((response) => response.data)
  },
  setDefaultLlmConfig(id) {
    return client.post(`${BASE}/llm-configs/${id}/set-default/`).then((response) => response.data)
  },

  // RAG 配置
  listRagConfigs(params = {}) {
    return client.get(`${BASE}/rag-configs/`, { params }).then((response) => response.data)
  },
  createRagConfig(data) {
    return client.post(`${BASE}/rag-configs/`, data).then((response) => response.data)
  },
  updateRagConfig(id, data) {
    return client.patch(`${BASE}/rag-configs/${id}/`, data).then((response) => response.data)
  },
  removeRagConfig(id) {
    return client.delete(`${BASE}/rag-configs/${id}/`).then((response) => response.data)
  },
  setDefaultRagConfig(id) {
    return client.post(`${BASE}/rag-configs/${id}/set-default/`).then((response) => response.data)
  },
  indexDocument(data) {
    return client.post(`${BASE}/rag/index/`, data).then((response) => response.data)
  },
  searchRag(data) {
    return client.post(`${BASE}/rag/search/`, data).then((response) => response.data)
  },
  ragStats(params = {}) {
    return client.get(`${BASE}/rag/stats/`, { params }).then((response) => response.data)
  },

  // MCP
  listMcpConfigs(params = {}) {
    return client.get(`${BASE}/mcp-configs/`, { params }).then((response) => response.data)
  },
  createMcpConfig(data) {
    return client.post(`${BASE}/mcp-configs/`, data).then((response) => response.data)
  },
  updateMcpConfig(id, data) {
    return client.patch(`${BASE}/mcp-configs/${id}/`, data).then((response) => response.data)
  },
  removeMcpConfig(id) {
    return client.delete(`${BASE}/mcp-configs/${id}/`).then((response) => response.data)
  },
  refreshMcpTools(id) {
    return client
      .post(`${BASE}/mcp-configs/${id}/refresh_tools/`)
      .then((response) => response.data)
  },
  listMcpTools(params = {}) {
    return client.get(`${BASE}/mcp-tools/`, { params }).then((response) => response.data)
  },

  // 用量
  listUsageLogs(params = {}) {
    return client.get(`${BASE}/usage-logs/`, { params }).then((response) => response.data)
  },
  usageStats(params = {}) {
    return client.get(`${BASE}/usage-stats/`, { params }).then((response) => response.data)
  },

  // Agent
  listAgents() {
    return client.get(`${BASE}/agents/`).then((response) => response.data)
  },
  runAgent(agentName, payload = {}) {
    return client
      .post(`${BASE}/agents/${agentName}/run/`, payload)
      .then((response) => response.data)
  },
}

export default aiCoreApi
