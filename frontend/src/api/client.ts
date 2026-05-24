import axios from 'axios';

/**
 * 创建axios实例
 * 统一配置基础URL、超时和请求头
 */
const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

/**
 * 响应拦截器 - 统一处理错误
 */
client.interceptors.response.use(
  (response) => response,
  (error) => {
    // 提取后端返回的错误信息
    const message = error.response?.data?.detail || error.message || '请求失败';
    console.error('[API Error]', message);
    return Promise.reject(error);
  }
);

export default client;
