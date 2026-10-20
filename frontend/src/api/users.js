import client from './client'

/** 用户目录（/api/users/），用于成员选择等场景。 */
export const usersApi = {
  list(params = {}) {
    return client.get('/users/', { params }).then((response) => response.data)
  },
  retrieve(id) {
    return client.get(`/users/${id}/`).then((response) => response.data)
  },
  brief(params = {}) {
    return client.get('/users/brief/', { params }).then((response) => response.data)
  },
}

export default usersApi
