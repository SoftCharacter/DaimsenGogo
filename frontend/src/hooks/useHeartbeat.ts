/**
 * 心跳Hook - 定期向后端发送心跳请求
 * 配合后端心跳监控机制，浏览器关闭时后端自动退出释放端口。
 * 心跳间隔10秒，使用navigator.sendBeacon在页面卸载时发送最后一次心跳。
 */
import { useEffect } from 'react'

/** 心跳发送间隔（毫秒） */
const HEARTBEAT_INTERVAL = 10_000
const HEARTBEAT_URL = 'http://127.0.0.1:8000/api/heartbeat'

/**
 * 发送心跳请求到后端
 * 使用fire-and-forget模式，不关心响应结果
 */
function sendHeartbeat(): void {
  fetch(HEARTBEAT_URL, { method: 'POST' }).catch(() => {
    /* 静默忽略心跳失败，后端不可达时无需前端处理 */
  })
}

/**
 * 挂载心跳定时器的Hook
 * 在App组件顶层调用，整个应用生命周期内保持心跳。
 * 页面关闭/刷新时通过beforeunload事件尝试发送最后一次通知。
 */
export function useHeartbeat(): void {
  useEffect(() => {
    /* 立即发送第一次心跳 */
    sendHeartbeat()

    /* 定时发送心跳 */
    const timer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL)

    /* 页面卸载时通过beacon发送关闭通知 */
    const handleUnload = () => {
      navigator.sendBeacon(HEARTBEAT_URL)
    }
    window.addEventListener('beforeunload', handleUnload)

    return () => {
      clearInterval(timer)
      window.removeEventListener('beforeunload', handleUnload)
    }
  }, [])
}
