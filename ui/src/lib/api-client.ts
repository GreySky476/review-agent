import axios from 'axios'

export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res,
  (error) => {
    // TODO: 登录页面未就绪，暂时不重定向
    // if (error.response?.status === 401) {
    //   window.location.href = '/login'
    // }
    return Promise.reject(error)
  },
)
