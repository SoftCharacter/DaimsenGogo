import client from './client'
import type { Theme, ThemeSummary } from '../types/theme'

/**
 * 主题管理API模块
 * 提供主题的增删改查接口，对应后端 /api/themes 路由
 */

/**
 * 获取所有主题摘要列表
 * 用于侧边栏展示主题概览信息
 * @returns 主题摘要数组
 */
export async function listThemes(): Promise<ThemeSummary[]> {
  const res = await client.get<ThemeSummary[]>('/themes/')
  return res.data
}

/**
 * 根据ID获取完整主题详情
 * 包含分类和股票等嵌套数据
 * @param id - 主题唯一标识
 * @returns 完整的主题对象
 */
export async function getTheme(id: string): Promise<Theme> {
  const res = await client.get<Theme>(`/themes/${id}`)
  return res.data
}

/**
 * 创建新的分析主题
 * @param theme - 主题数据（不含id，后端自动生成）
 * @returns 创建成功后返回的完整主题对象（包含id）
 */
export async function createTheme(theme: Theme): Promise<Theme> {
  const res = await client.post<Theme>('/themes/', theme)
  return res.data
}

/**
 * 更新指定主题
 * 全量替换主题数据
 * @param id - 需要更新的主题ID
 * @param theme - 更新后的完整主题数据
 * @returns 更新后的主题对象
 */
export async function updateTheme(id: string, theme: Theme): Promise<Theme> {
  const res = await client.put<Theme>(`/themes/${id}`, theme)
  return res.data
}

/**
 * 删除指定主题
 * @param id - 需要删除的主题ID
 */
export async function deleteTheme(id: string): Promise<void> {
  await client.delete(`/themes/${id}`)
}
