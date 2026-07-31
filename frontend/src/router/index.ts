import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores'
import { setLoginRedirectHandler } from '@/api/auth-redirect'
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
  // 认证相关
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: { title: 'auth.login', redirectAuthenticated: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/Register.vue'),
    meta: { title: 'auth.register', redirectAuthenticated: true }
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('@/views/auth/ForgotPassword.vue'),
    meta: { title: 'auth.forgotPassword', redirectAuthenticated: true }
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
    meta: { title: 'workflow.title' }
  },
  {
    path: '/research-boards',
    name: 'ResearchBoards',
    component: () => import('@/views/research-boards/index.vue'),
    meta: { title: 'nav.researchBoards', requiresAuth: true }
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
        path: 'tools/create',
        name: 'AdminToolCreate',
        component: () => import('@/views/tools/Create.vue'),
        meta: { title: 'tools.createTool' }
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
        path: 'tool-categories',
        name: 'AdminToolCategories',
        component: () => import('@/views/admin/ToolCategories.vue'),
        meta: { title: 'admin.toolCategories' }
      },
      {
        path: 'workbench-groups',
        name: 'AdminWorkbenchGroups',
        component: () => import('@/views/admin/WorkbenchGroups.vue'),
        meta: { title: 'admin.workbenchGroups' }
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

  // 设置页面标题
  const titleKey = typeof to.meta.title === 'string' ? to.meta.title : ''
  const translatedTitle = titleKey ? i18n.global.t(titleKey) : 'CPUModel'
  document.title = `${translatedTitle} - CPUModel`

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
    requiresAuth?: boolean
    requiresAdmin?: boolean
    redirectAuthenticated?: boolean
  }
}
