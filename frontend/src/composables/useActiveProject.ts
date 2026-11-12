import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listProjects } from '@/api/projects'
import { resolveActiveProjectId, resolveProjectSwitchTarget } from '@/domain/projects/project-switch'
import type { ResearchProject } from '@/types/projects'

/**
 * 当前项目上下文（侧边栏项目切换器用）。
 *
 * 项目列表是跨页面共享的：一个会话里项目不会频繁变化，每次导航都重拉一遍既慢又闪，
 * 所以列表与加载态放在模块作用域，只有显式 `refresh()` 才会重新拉。
 */
const projects = ref<ResearchProject[]>([])
const loading = ref(false)
let loadedOnce = false

async function ensureProjects(): Promise<void> {
  if (loadedOnce || loading.value) return
  loading.value = true
  try {
    const response = await listProjects()
    projects.value = response.data.items ?? []
    loadedOnce = true
  } catch {
    projects.value = []
  } finally {
    loading.value = false
  }
}

function refresh(): void {
  loadedOnce = false
  void ensureProjects()
}

export function useActiveProject() {
  const route = useRoute()
  const router = useRouter()

  const activeProjectId = computed(() => resolveActiveProjectId(route.params, route.query))

  const activeProject = computed(
    () => projects.value.find(project => project.id === activeProjectId.value) ?? null
  )

  const projectOptions = computed(() =>
    projects.value.map(project => ({ value: project.id, label: project.name }))
  )

  /**
   * 换项目时尽量留在当前界面（`/projects/:id/targets` → 同页面换 id，
   * `/tasks?project_id=` → 同页面换参数），只有当前页面与项目无关时才回到项目总览。
   */
  async function switchProject(projectId: string): Promise<void> {
    if (!projectId || projectId === activeProjectId.value) return
    const target = resolveProjectSwitchTarget(
      {
        name: typeof route.name === 'string' ? route.name : null,
        path: route.path,
        params: route.params as Record<string, unknown>,
        query: route.query as Record<string, unknown>
      },
      projectId
    )
    await router.push(target as Parameters<typeof router.push>[0])
  }

  return {
    projects,
    loading,
    activeProjectId,
    activeProject,
    projectOptions,
    ensureProjects,
    refresh,
    switchProject
  }
}
