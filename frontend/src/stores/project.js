import { defineStore } from 'pinia'

import { projectsApi } from '@/api/projects'

/** 项目上下文：项目列表、当前项目、切换。 */
export const useProjectStore = defineStore('project', {
  state: () => ({
    projects: [],
    currentProjectId: null,
    loading: false,
    loaded: false,
  }),

  getters: {
    currentProject: (state) =>
      state.projects.find((project) => project.id === state.currentProjectId) || null,
    currentProjectName: (state) =>
      state.projects.find((project) => project.id === state.currentProjectId)?.name || '',
    options: (state) =>
      state.projects.map((project) => ({
        label: project.name,
        value: project.id,
        project_type: project.project_type,
      })),
  },

  actions: {
    async fetchProjects(params = {}) {
      this.loading = true
      try {
        const data = await projectsApi.list({ page_size: 100, ...params })
        this.projects = Array.isArray(data?.results) ? data.results : []
        this.loaded = true
        const exists = this.projects.some((project) => project.id === this.currentProjectId)
        if (!exists) {
          this.currentProjectId = this.projects[0]?.id ?? null
        }
        return data
      } finally {
        this.loading = false
      }
    },

    setCurrentProject(project) {
      if (project === null || project === undefined) {
        this.currentProjectId = null
        return null
      }
      const id = typeof project === 'object' ? project.id : project
      this.currentProjectId = id
      return this.currentProject
    },

    /** Align the current project with the module being opened.
     *
     * Each test module is project-type specific (api-testing -> api, etc.).
     * Opening a module while another type is selected would show an empty
     * workspace, so we transparently switch to the first matching project.
     */
    async alignToProjectType(projectType) {
      if (!projectType) return
      if (!this.loaded) {
        try {
          await this.fetchProjects()
        } catch (error) {
          return
        }
      }
      const current = this.currentProject
      if (current && current.project_type === projectType) return
      const match = this.projects.find(
        (project) => project.project_type === projectType && project.is_active !== false,
      )
      if (match) {
        this.currentProjectId = match.id
      }
    },

    upsertProject(project) {
      if (!project?.id) return
      const index = this.projects.findIndex((item) => item.id === project.id)
      if (index >= 0) this.projects.splice(index, 1, { ...this.projects[index], ...project })
      else this.projects.unshift(project)
      if (!this.currentProjectId) this.currentProjectId = project.id
    },

    removeProject(id) {
      this.projects = this.projects.filter((project) => project.id !== id)
      if (this.currentProjectId === id) this.currentProjectId = this.projects[0]?.id ?? null
    },

    clear() {
      this.projects = []
      this.currentProjectId = null
      this.loaded = false
    },
  },

  persist: {
    key: 'aits-project',
    paths: ['currentProjectId'],
  },
})
