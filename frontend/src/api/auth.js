import client from './client'

/** 认证 / 当前用户接口（/api/auth/）。 */
export const authApi = {
  login(data) {
    return client.post('/auth/login/', data).then((response) => response.data)
  },
  register(data) {
    return client.post('/auth/register/', data).then((response) => response.data)
  },
  refresh(refresh) {
    return client.post('/auth/refresh/', { refresh }).then((response) => response.data)
  },
  verify(token) {
    return client.post('/auth/verify/', { token }).then((response) => response.data)
  },
  logout(refresh) {
    return client.post('/auth/logout/', { refresh }).then((response) => response.data)
  },
  me() {
    return client.get('/auth/me/').then((response) => response.data)
  },
  updateMe(data) {
    return client.patch('/auth/me/', data).then((response) => response.data)
  },
  changePassword(data) {
    return client.post('/auth/change-password/', data).then((response) => response.data)
  },
}

export default authApi
