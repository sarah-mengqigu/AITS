import client from './client'

const BASE = '/notifications'

/** 通知中心（/api/notifications/）。 */
export const notificationsApi = {
  // 渠道
  listChannels(params = {}) {
    return client.get(`${BASE}/channels/`, { params }).then((response) => response.data)
  },
  retrieveChannel(id) {
    return client.get(`${BASE}/channels/${id}/`).then((response) => response.data)
  },
  createChannel(data) {
    return client.post(`${BASE}/channels/`, data).then((response) => response.data)
  },
  updateChannel(id, data) {
    return client.patch(`${BASE}/channels/${id}/`, data).then((response) => response.data)
  },

  // 接收人
  listReceivers(params = {}) {
    return client.get(`${BASE}/receivers/`, { params }).then((response) => response.data)
  },
  retrieveReceiver(id) {
    return client.get(`${BASE}/receivers/${id}/`).then((response) => response.data)
  },
  createReceiver(data) {
    return client.post(`${BASE}/receivers/`, data).then((response) => response.data)
  },
  updateReceiver(id, data) {
    return client.patch(`${BASE}/receivers/${id}/`, data).then((response) => response.data)
  },
  removeReceiver(id) {
    return client.delete(`${BASE}/receivers/${id}/`).then((response) => response.data)
  },

  // 邮件配置（单例）
  emailConfig() {
    return client.get(`${BASE}/email-config/`).then((response) => response.data)
  },
  saveEmailConfig(data, { partial = false } = {}) {
    const method = partial ? client.patch : client.put
    return method(`${BASE}/email-config/`, data).then((response) => response.data)
  },

  // 测试发送
  test(data) {
    return client.post(`${BASE}/test/`, data).then((response) => response.data)
  },

  // 日志
  listLogs(params = {}) {
    return client.get(`${BASE}/logs/`, { params }).then((response) => response.data)
  },
  retrieveLog(id) {
    return client.get(`${BASE}/logs/${id}/`).then((response) => response.data)
  },
}

export default notificationsApi
