import { get, post } from './request'
import type { ProjectCreateInput, ResearchProject } from '@/types/projects'

export const listProjects = () =>
  get<{ items: ResearchProject[] }>('/projects', undefined, { silent: true, retry: 1 })

export const createProject = (data: ProjectCreateInput) =>
  post<ResearchProject>('/projects', data, { silent: true })
