import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

vi.mock('@/api/projects', () => ({
  projectsApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}))

import { projectsApi } from '@/api/projects'
import { useProjectStore } from '@/stores/project'

const PROJECTS = {
  results: [
    { id: 1, name: 'API 项目', project_type: 'api', is_active: true },
    { id: 2, name: 'Web 项目', project_type: 'web', is_active: true },
    { id: 3, name: '性能项目', project_type: 'perf', is_active: true },
  ],
}

function createTestPinia() {
  const pinia = createPinia()
  pinia.use(piniaPluginPersistedstate)
  createApp({}).use(pinia)
  setActivePinia(pinia)
  return pinia
}

describe('stores/project', () => {
  beforeEach(() => {
    createTestPinia()
    vi.clearAllMocks()
    projectsApi.list.mockResolvedValue(PROJECTS)
  })

  it('fetchProjects 默认选中第一个项目', async () => {
    const store = useProjectStore()
    await store.fetchProjects()
    expect(store.projects).toHaveLength(3)
    expect(store.currentProjectId).toBe(1)
    expect(store.currentProjectName).toBe('API 项目')
  })

  it('alignToProjectType 在类型不匹配时自动切换', async () => {
    const store = useProjectStore()
    await store.fetchProjects()
    store.setCurrentProject(1) // api
    await store.alignToProjectType('web')
    expect(store.currentProjectId).toBe(2)
    expect(store.currentProject.project_type).toBe('web')
  })

  it('alignToProjectType 类型已匹配时不切换', async () => {
    const store = useProjectStore()
    await store.fetchProjects()
    store.setCurrentProject(2) // web
    await store.alignToProjectType('web')
    expect(store.currentProjectId).toBe(2)
  })

  it('alignToProjectType 无匹配项目时保持原选择', async () => {
    const store = useProjectStore()
    await store.fetchProjects()
    store.setCurrentProject(1)
    await store.alignToProjectType('app')
    expect(store.currentProjectId).toBe(1)
  })

  it('upsertProject 新增项目并可在没有当前项目时选中', async () => {
    const store = useProjectStore()
    store.upsertProject({ id: 9, name: '新项目', project_type: 'app' })
    expect(store.projects[0].name).toBe('新项目')
    expect(store.currentProjectId).toBe(9)
  })

  it('removeProject 删除当前项目后回落到第一个', async () => {
    const store = useProjectStore()
    await store.fetchProjects()
    store.setCurrentProject(2)
    store.removeProject(2)
    expect(store.currentProjectId).toBe(1)
  })
})
