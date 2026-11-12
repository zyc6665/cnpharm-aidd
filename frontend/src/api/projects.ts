import { del, get, patch, post } from './request'
import type {
  ProjectMember,
  ProjectMemberCreateInput,
  ProjectMemberUpdateInput,
  ProjectCreateInput,
  ProjectOverview,
  ResearchProject
} from '@/types/projects'

/**
 * 项目列表。默认按后端口径隐藏归档项目；工作台需要单独展示「已归档」分组，
 * 所以显式传 `includeArchived: true` 拉全量再本地分组。
 */
export const listProjects = (options: { includeArchived?: boolean } = {}) =>
  get<{ items: ResearchProject[] }>(
    '/projects',
    options.includeArchived ? { include_archived: true } : undefined,
    { silent: true, retry: 1 }
  )

export const createProject = (data: ProjectCreateInput) =>
  post<ResearchProject>('/projects', data, { silent: true })

export const getProjectOverview = (projectId: string) =>
  get<ProjectOverview>(`/projects/${projectId}/overview`, undefined, { silent: true, retry: 1 })

export const archiveProject = (projectId: string) =>
  post<ResearchProject>(`/projects/${projectId}/archive`, undefined, { silent: true })

export const unarchiveProject = (projectId: string) =>
  post<ResearchProject>(`/projects/${projectId}/unarchive`, undefined, { silent: true })

export const deleteProject = (projectId: string) =>
  del<{ id: string }>(`/projects/${projectId}`, { silent: true })

export const listProjectMembers = (projectId: string) =>
  get<{ items: ProjectMember[] }>(`/projects/${projectId}/members`, undefined, {
    silent: true,
    retry: 1
  })

export const addProjectMember = (projectId: string, data: ProjectMemberCreateInput) =>
  post<ProjectMember>(`/projects/${projectId}/members`, data, { silent: true })

export const updateProjectMember = (
  projectId: string,
  membershipId: string,
  data: ProjectMemberUpdateInput
) => patch<ProjectMember>(`/projects/${projectId}/members/${membershipId}`, data, { silent: true })

export const removeProjectMember = (projectId: string, membershipId: string) =>
  del<{ id: string }>(`/projects/${projectId}/members/${membershipId}`, { silent: true })
