import { del, get, post } from './request'
import type { ProjectCreateInput, ProjectOverview, ResearchProject } from '@/types/projects'

export const listProjects = () =>
  get<{ items: ResearchProject[] }>('/projects', undefined, { silent: true, retry: 1 })

export const createProject = (data: ProjectCreateInput) =>
  post<ResearchProject>('/projects', data, { silent: true })

export const getProjectOverview = (projectId: string) =>
  get<ProjectOverview>(`/projects/${projectId}/overview`, undefined, { silent: true, retry: 1 })

export const archiveProject = (projectId: string) =>
  post<ResearchProject>(`/projects/${projectId}/archive`, undefined, { silent: true })

export const deleteProject = (projectId: string) =>
  del<{ id: string }>(`/projects/${projectId}`, { silent: true })
