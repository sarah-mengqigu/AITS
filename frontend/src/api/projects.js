import client, { API_BASE } from './client'

/** 项目 / 成员 / 环境 / 文件 / 知识库 / 第三方配置（/api/projects/）。 */
export const projectsApi = {
  list(params = {}) {
    return client.get('/projects/', { params }).then((response) => response.data)
  },
  retrieve(id) {
    return client.get(`/projects/${id}/`).then((response) => response.data)
  },
  create(data) {
    return client.post('/projects/', data).then((response) => response.data)
  },
  update(id, data) {
    return client.patch(`/projects/${id}/`, data).then((response) => response.data)
  },
  remove(id) {
    return client.delete(`/projects/${id}/`).then((response) => response.data)
  },
  stats(id) {
    return client.get(`/projects/${id}/stats/`).then((response) => response.data)
  },

  // 成员
  members(id) {
    return client.get(`/projects/${id}/members/`).then((response) => response.data)
  },
  addMember(id, data) {
    return client.post(`/projects/${id}/members/add/`, data).then((response) => response.data)
  },
  updateMember(memberId, data) {
    return client.patch(`/projects/members/${memberId}/`, data).then((response) => response.data)
  },
  removeMember(id, memberId) {
    return client.delete(`/projects/${id}/members/${memberId}/`).then((response) => response.data)
  },

  // 第三方配置
  thirdPartyConfig(id) {
    return client.get(`/projects/${id}/third-party-config/`).then((response) => response.data)
  },
  saveThirdPartyConfig(id, data, { partial = false } = {}) {
    const method = partial ? client.patch : client.put
    return method(`/projects/${id}/third-party-config/`, data).then((response) => response.data)
  },

  // 环境
  listEnvironments(params = {}) {
    return client.get('/projects/environments/', { params }).then((response) => response.data)
  },
  createEnvironment(data) {
    return client.post('/projects/environments/', data).then((response) => response.data)
  },
  updateEnvironment(id, data) {
    return client.patch(`/projects/environments/${id}/`, data).then((response) => response.data)
  },
  removeEnvironment(id) {
    return client.delete(`/projects/environments/${id}/`).then((response) => response.data)
  },
  setDefaultEnvironment(id) {
    return client
      .post(`/projects/environments/${id}/set-default/`)
      .then((response) => response.data)
  },

  // 上传文件（multipart: project / file / purpose）
  listFiles(params = {}) {
    return client.get('/projects/files/', { params }).then((response) => response.data)
  },
  uploadFile(projectId, file, purpose = 'generic') {
    const form = new FormData()
    form.append('project', projectId)
    form.append('file', file)
    form.append('purpose', purpose)
    return client
      .post('/projects/files/', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((response) => response.data)
  },
  removeFile(id) {
    return client.delete(`/projects/files/${id}/`).then((response) => response.data)
  },
  fileDownloadUrl(id) {
    return `${API_BASE}/projects/files/${id}/download/`
  },

  // 知识库
  listKnowledge(params = {}) {
    return client.get('/projects/knowledge/', { params }).then((response) => response.data)
  },
  createKnowledge(data) {
    return client.post('/projects/knowledge/', data).then((response) => response.data)
  },
  updateKnowledge(id, data) {
    return client.patch(`/projects/knowledge/${id}/`, data).then((response) => response.data)
  },
  removeKnowledge(id) {
    return client.delete(`/projects/knowledge/${id}/`).then((response) => response.data)
  },
  reindexKnowledge(id) {
    return client.post(`/projects/knowledge/${id}/reindex/`).then((response) => response.data)
  },
}

export default projectsApi
