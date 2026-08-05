import { del, get, patch, post } from './request'
import type {
  ProjectMember,
  ProjectMemberCreateInput,
  ProjectMemberUpdateInput,
  ProjectCreateInput,
  ProjectOverview,
  ResearchProject
} from '@/types/projects'

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
