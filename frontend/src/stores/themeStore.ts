import { create } from 'zustand'
import type { Theme, ThemeSummary } from '../types/theme'
import * as themeApi from '../api/themeApi'

/**
 * 主题Store状态接口
 * 定义主题管理相关的状态字段和操作方法
 */
interface ThemeState {
  themes: ThemeSummary[]       // 主题摘要列表（侧边栏展示用）
  currentTheme: Theme | null   // 当前选中的完整主题详情
  loading: boolean             // 是否正在加载数据
  error: string | null         // 错误信息

  /** 获取所有主题摘要列表 */
  fetchThemes: () => Promise<void>
  /** 根据ID获取完整主题详情 */
  fetchTheme: (id: string) => Promise<void>
  /** 创建新主题 */
  createTheme: (theme: Theme) => Promise<Theme>
  /** 更新指定主题 */
  updateTheme: (id: string, theme: Theme) => Promise<Theme>
  /** 删除指定主题 */
  deleteTheme: (id: string) => Promise<void>
  /** 手动设置当前选中主题（本地操作，不请求后端） */
  setCurrentTheme: (theme: Theme | null) => void
}

/**
 * 主题状态管理Store
 * 使用zustand管理主题列表和当前选中主题的全局状态
 */
let themeFetchSeq = 0

export const useThemeStore = create<ThemeState>((set) => ({
  /* ---------- 初始状态 ---------- */
  themes: [],
  currentTheme: null,
  loading: false,
  error: null,

  /**
   * 从后端获取主题摘要列表
   * 设置loading状态，失败时记录错误信息
   */
  fetchThemes: async () => {
    set({ loading: true, error: null })
    try {
      const themes = await themeApi.listThemes()
      set({ themes, loading: false })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : '获取主题列表失败'
      set({ error: message, loading: false })
    }
  },

  /**
   * 根据ID获取完整主题详情并设为当前选中
   * @param id - 主题唯一标识
   */
  fetchTheme: async (id: string) => {
    const seq = themeFetchSeq + 1
    themeFetchSeq = seq
    set({ loading: true, error: null })
    try {
      const theme = await themeApi.getTheme(id)
      if (themeFetchSeq !== seq) return
      set({ currentTheme: theme, loading: false })
    } catch (e: unknown) {
      if (themeFetchSeq !== seq) return
      const message = e instanceof Error ? e.message : '获取主题详情失败'
      set({ error: message, loading: false })
    }
  },

  /**
   * 创建新主题
   * 创建成功后自动追加到本地主题列表中
   * @param theme - 主题数据
   * @returns 创建后包含ID的完整主题对象
   */
  createTheme: async (theme: Theme) => {
    set({ loading: true, error: null })
    try {
      const created = await themeApi.createTheme(theme)
      // 将新主题的摘要信息追加到列表末尾
      const summary: ThemeSummary = {
        id: created.id,
        name: created.name,
        description: created.description,
        updated_at: created.updated_at,
      }
      set((state) => ({
        themes: [...state.themes, summary],
        currentTheme: created,
        loading: false,
      }))
      return created
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : '创建主题失败'
      set({ error: message, loading: false })
      throw e
    }
  },

  /**
   * 更新指定主题
   * 更新成功后同步更新本地列表和当前选中主题
   * @param id - 主题ID
   * @param theme - 更新后的主题数据
   */
  updateTheme: async (id: string, theme: Theme) => {
    set({ loading: true, error: null })
    try {
      const updated = await themeApi.updateTheme(id, theme)
      // 同步更新本地主题列表中对应条目的摘要信息
      set((state) => ({
        themes: state.themes.map((t) =>
          t.id === id
            ? { id: updated.id, name: updated.name, description: updated.description, updated_at: updated.updated_at }
            : t
        ),
        // 如果更新的是当前选中的主题，同步刷新详情
        currentTheme: state.currentTheme?.id === id ? updated : state.currentTheme,
        loading: false,
      }))
      return updated
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : '更新主题失败'
      set({ error: message, loading: false })
      throw e
    }
  },

  /**
   * 删除指定主题
   * 删除成功后从本地列表移除，如果是当前选中则清空
   * @param id - 主题ID
   */
  deleteTheme: async (id: string) => {
    set({ loading: true, error: null })
    try {
      await themeApi.deleteTheme(id)
      // 从本地列表中移除已删除的主题
      set((state) => ({
        themes: state.themes.filter((t) => t.id !== id),
        // 如果删除的是当前选中主题，清空选中状态
        currentTheme: state.currentTheme?.id === id ? null : state.currentTheme,
        loading: false,
      }))
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : '删除主题失败'
      set({ error: message, loading: false })
    }
  },

  /**
   * 手动设置当前选中主题
   * 纯本地操作，不发起后端请求
   * @param theme - 主题对象或null（清空选中）
   */
  setCurrentTheme: (theme: Theme | null) => {
    set({ currentTheme: theme })
  },
}))
