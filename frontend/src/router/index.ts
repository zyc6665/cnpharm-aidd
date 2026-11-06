import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores'
import { setLoginRedirectHandler } from '@/api/auth-redirect'
import { buildDocumentTitle } from '@/config/brand'
import i18n from '@/locales'

// 路由配置
const routes: RouteRecordRaw[] = [
  // 首页（品牌页）
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/home/index.vue'),
    meta: { title: 'home.title' }
  },
  // 工作台仪表盘（登录后默认页）
  {
    path: '/workspace',
    name: 'Workspace',
    component: () => import('@/views/workspace/index.vue'),
    meta: { title: 'nav.workspace', requiresAuth: true }
  },
  {
    path: '/projects/:projectId',
    name: 'ProjectOverview',
    component: () => import('@/views/projects/Overview.vue'),
    meta: { titleLiteral: '项目总览', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/lineage',
    name: 'ProjectArtifactLineage',
    component: () => import('@/views/projects/ArtifactLineage.vue'),
    meta: { titleLiteral: 'Artifact 谱系', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/settings',
    name: 'ProjectSettings',
    component: () => import('@/views/projects/Settings.vue'),
    meta: { titleLiteral: '项目设置', requiresAuth: true }
  },
  // 靶点与结构（P-06~P-11）
  {
    path: '/projects/:projectId/targets',
    name: 'ProjectTargets',
    component: () => import('@/views/targets/List.vue'),
    meta: { title: 'targets.list.title', requiresAuth: true }
  },
  {
    path: '/targets/:targetId',
    name: 'TargetDetail',
    component: () => import('@/views/targets/Detail.vue'),
    meta: { title: 'targets.detail.title', requiresAuth: true }
  },
  {
    path: '/proteins/:proteinId/predict',
    name: 'StructurePredict',
    component: () => import('@/views/targets/Predict.vue'),
    meta: { title: 'targets.predict.title', requiresAuth: true }
  },
  {
    path: '/structures/:structureId/pockets',
    name: 'StructurePockets',
    component: () => import('@/views/targets/Pockets.vue'),
    meta: { title: 'targets.pockets.title', requiresAuth: true }
  },
  {
    path: '/structures/:structureId',
    name: 'StructureDetail',
    component: () => import('@/views/targets/StructureDetail.vue'),
    meta: { title: 'targets.structure.title', requiresAuth: true }
  },
  {
    path: '/pockets/:pocketId/residues',
    name: 'PocketResidues',
    component: () => import('@/views/targets/PocketResidues.vue'),
    meta: { title: 'targets.residues.title', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/workflow',
    name: 'ProjectWorkflow',
    component: () => import('@/views/workflow/index.vue'),
    meta: { titleLiteral: '项目工作流', requiresAuth: true }
  },
  // 认证相关
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: { title: 'auth.login', redirectAuthenticated: true }
  },
  // 工具相关
  {
    path: '/tools',
    name: 'Tools',
    component: () => import('@/views/tools/List.vue'),
    meta: { title: 'tools.title' }
  },
  {
    path: '/workflow',
    name: 'Workflow',
    component: () => import('@/views/workflow/index.vue'),
    meta: { title: 'workflow.title', requiresAuth: true }
  },
  {
    path: '/achievements',
    name: 'Achievements',
    component: () => import('@/views/demo/Achievements.vue'),
    meta: { title: 'nav.achievements', requiresAuth: true }
  },
  {
    path: '/workflow/runs/:runId',
    name: 'WorkflowRunDetail',
    component: () => import('@/views/workflow/RunDetail.vue'),
    meta: { titleLiteral: '工作流运行详情', requiresAuth: true }
  },
  // 设计（分子生成 / 多肽设计 / 生成结果）
  {
    path: '/design',
    name: 'DesignPipeline',
    component: () => import('@/views/design/Pipeline.vue'),
    meta: { title: 'design.pipeline.title', requiresAuth: true }
  },
  {
    path: '/design/molecules',
    name: 'MoleculeGeneration',
    component: () => import('@/views/design/MoleculeGeneration.vue'),
    meta: { title: 'design.molecule.title', requiresAuth: true }
  },
  {
    path: '/design/peptides',
    name: 'PeptideDesign',
    component: () => import('@/views/design/PeptideDesign.vue'),
    meta: { title: 'design.peptide.title', requiresAuth: true }
  },
  {
    path: '/design/runs',
    redirect: { path: '/tasks', query: { type: 'design' } }
  },
  {
    path: '/tasks/:id/result',
    name: 'TaskResult',
    component: () => import('@/views/tasks/Result.vue'),
    meta: { title: 'tasks.resultPage.title', requiresAuth: true }
  },
  {
    path: '/tasks/:id/results',
    name: 'GenerationResults',
    component: () => import('@/views/design/GenerationResults.vue'),
    meta: { title: 'design.results.title', requiresAuth: true }
  },
  // 性质预测 / 虚拟筛选（P-21 ~ P-25）
  {
    path: '/predict',
    name: 'PropertyPredict',
    component: () => import('@/views/predict/PropertyPredictSubmit.vue'),
    meta: { title: 'predict.submit.title', requiresAuth: true }
  },
  {
    path: '/tasks/:id/predictions',
    name: 'PropertyPredictResult',
    component: () => import('@/views/predict/PropertyPredictResult.vue'),
    meta: { title: 'predict.result.title', requiresAuth: true }
  },
  {
    path: '/screen',
    name: 'ScreenConfig',
    component: () => import('@/views/screening/ScreenConfig.vue'),
    meta: { title: 'screening.config.title', requiresAuth: true }
  },
  {
    path: '/tasks/:id/screening',
    name: 'ScreenResult',
    component: () => import('@/views/screening/ScreenResult.vue'),
    meta: { title: 'screening.result.title', requiresAuth: true }
  },
  {
    path: '/docking-results/:id',
    name: 'DockingResultDetail',
    component: () => import('@/views/screening/DockingResultDetail.vue'),
    meta: { title: 'screening.detail.title', requiresAuth: true }
  },
  // MD / 自由能页面
  {
    path: '/md',
    name: 'MdSubmit',
    component: () => import('@/views/md/MdSubmit.vue'),
    meta: { title: 'md.submit.title', requiresAuth: true }
  },
  {
    path: '/tasks/:id/md',
    name: 'MdResult',
    component: () => import('@/views/md/MdResult.vue'),
    meta: { title: 'md.result.title', requiresAuth: true }
  },
  {
    path: '/tasks/:id/free-energy',
    name: 'FreeEnergyResult',
    component: () => import('@/views/md/FreeEnergyResult.vue'),
    meta: { title: 'md.freeEnergy.title', requiresAuth: true }
  },
  // 化合物 / 候选物 / 结果
  {
    path: '/projects/:projectId/assets',
    name: 'ProjectAssets',
    component: () => import('@/views/compounds/Assets.vue'),
    meta: { titleLiteral: '数据资产', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/candidates',
    name: 'ProjectCandidates',
    component: () => import('@/views/compounds/Candidates.vue'),
    meta: { titleLiteral: '候选物', requiresAuth: true }
  },
  {
    path: '/compounds/:compoundId',
    name: 'CompoundDetail',
    component: () => import('@/views/compounds/CompoundDetail.vue'),
    meta: { titleLiteral: '化合物详情', requiresAuth: true }
  },
  {
    path: '/candidate-sets/:setId',
    name: 'CandidateSetDetail',
    component: () => import('@/views/compounds/CandidateSetDetail.vue'),
    meta: { titleLiteral: '候选集详情', requiresAuth: true }
  },
  {
    path: '/candidates/:candidateId',
    name: 'CandidateDetail',
    component: () => import('@/views/compounds/CandidateDetail.vue'),
    meta: { titleLiteral: '候选物详情', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/candidates/compare',
    name: 'CandidateCompare',
    component: () => import('@/views/compounds/Compare.vue'),
    meta: { titleLiteral: '候选物对比', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/results',
    name: 'ProjectResults',
    component: () => import('@/views/results/List.vue'),
    meta: { titleLiteral: '结果中心', requiresAuth: true }
  },
  {
    path: '/projects/:projectId/decisions',
    name: 'ProjectDecisions',
    component: () => import('@/views/projects/Decisions.vue'),
    meta: { titleLiteral: '决策记录', requiresAuth: true }
  },
  {
    path: '/results/:taskId',
    name: 'ResultDetail',
    component: () => import('@/views/results/ResultDetail.vue'),
    meta: { titleLiteral: '结果详情', requiresAuth: true }
  },
  {
    path: '/tools/:id',
    name: 'ToolDetail',
    component: () => import('@/views/tools/Detail.vue'),
    meta: { title: 'tools.detail' }
  },
  // 任务相关
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('@/views/tasks/List.vue'),
    meta: { title: 'tasks.title', requiresAuth: true }
  },
  {
    path: '/tasks/:id',
    name: 'TaskDetail',
    component: () => import('@/views/tasks/Detail.vue'),
    meta: { title: 'tasks.detail', requiresAuth: true }
  },
  // 用户中心
  {
    path: '/user',
    name: 'UserCenter',
    component: () => import('@/views/user/index.vue'),
    meta: { title: 'user.title', requiresAuth: true },
    children: [
      {
        path: '',
        name: 'UserProfile',
        component: () => import('@/views/user/Profile.vue'),
        meta: { title: 'user.profile' }
      },
      {
        path: 'settings',
        name: 'UserSettings',
        component: () => import('@/views/user/Settings.vue'),
        meta: { title: 'user.settings' }
      },
      {
        path: 'favorites',
        name: 'UserFavorites',
        component: () => import('@/views/user/Favorites.vue'),
        meta: { title: 'user.favorites' }
      }
    ]
  },
  // 管理后台（AppShell 提供侧边栏，admin/index.vue 提供 tabs）
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/admin/index.vue'),
    meta: { title: 'admin.title', requiresAuth: true, requiresAdmin: true },
    redirect: '/admin/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'AdminDashboard',
        component: () => import('@/views/admin/Dashboard.vue'),
        meta: { title: 'admin.dashboard' }
      },
      {
        path: 'users',
        name: 'AdminUsers',
        component: () => import('@/views/admin/Users.vue'),
        meta: { title: 'admin.users' }
      },
      {
        path: 'tools/:id/edit',
        name: 'AdminToolEdit',
        component: () => import('@/views/tools/Create.vue'),
        meta: { title: 'tools.editTool' }
      },
      {
        path: 'tools',
        name: 'AdminTools',
        component: () => import('@/views/admin/Tools.vue'),
        meta: { title: 'admin.tools' }
      },
      {
        path: 'tool-packages',
        name: 'AdminToolPackages',
        component: () => import('@/views/admin/ToolPackages.vue'),
        meta: { title: 'admin.toolPackages' }
      },
      {
        path: 'tool-categories',
        name: 'AdminToolCategories',
        component: () => import('@/views/admin/ToolCategories.vue'),
        meta: { title: 'admin.toolCategories' }
      },
      {
        path: 'model-guide',
        name: 'AdminModelGuide',
        component: () => import('@/views/admin/ModelGuide.vue'),
        meta: { title: 'admin.modelGuide' }
      },
      {
        path: 'tasks',
        name: 'AdminTasks',
        component: () => import('@/views/admin/Tasks.vue'),
        meta: { title: 'admin.tasks' }
      },
      {
        path: 'system',
        name: 'AdminSystem',
        component: () => import('@/views/admin/System.vue'),
        meta: { title: 'admin.system' }
      },
      {
        path: 'compute',
        name: 'AdminCompute',
        component: () => import('@/views/admin/Compute.vue'),
        meta: { title: 'admin.compute.title' }
      },
      {
        path: 'audit',
        name: 'AdminAudit',
        component: () => import('@/views/admin/Audit.vue'),
        meta: { title: 'admin.audit.title' }
      }
    ]
  },
  // 错误页面
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/403.vue'),
    meta: { title: 'error.forbidden' }
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: 'error.notFound' }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/404'
  }
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

setLoginRedirectHandler((redirectPath: string) => {
  router.push({ name: 'Login', query: { redirect: redirectPath } })
})

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()

  // 认证依赖 httpOnly Cookie，首次导航时先用 /users/me 恢复会话，
  // 避免已登录用户被误判为未登录而跳转登录页。
  if (!userStore.authReady) {
    await userStore.bootstrapAuthState()
  }

  // 设置页面标题
  const titleKey = typeof to.meta.title === 'string' ? to.meta.title : ''
  const translatedTitle = typeof to.meta.titleLiteral === 'string'
    ? to.meta.titleLiteral
    : titleKey ? i18n.global.t(titleKey) : ''
  document.title = buildDocumentTitle(translatedTitle)

  // 认证页面（已登录用户重定向到工作台）
  if (to.meta.redirectAuthenticated && userStore.isLoggedIn) {
    next('/workspace')
    return
  }

  // 首页访问（已登录用户重定向到工作台）
  if (to.path === '/' && userStore.isLoggedIn) {
    next('/workspace')
    return
  }

  // 需要登录的页面
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  // 需要管理员权限的页面
  if (to.meta.requiresAdmin) {
    // 如果还没有用户信息，先获取
    if (!userStore.userInfo) {
      await userStore.fetchUserInfo()
    }
    if (!userStore.isAdmin) {
      next('/403')
      return
    }
  }

  next()
})

export default router

// 类型声明
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    titleLiteral?: string
    requiresAuth?: boolean
    requiresAdmin?: boolean
    redirectAuthenticated?: boolean
    focusMode?: boolean
  }
}
