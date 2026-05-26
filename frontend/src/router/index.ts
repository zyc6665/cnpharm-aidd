import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores'

// 路由配置
const routes: RouteRecordRaw[] = [
  // 首页
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/home/index.vue'),
    meta: { title: 'home.title' }
  },
  // 认证相关
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: { title: 'auth.login', guest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/Register.vue'),
    meta: { title: 'auth.register', guest: true }
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('@/views/auth/ForgotPassword.vue'),
    meta: { title: 'auth.forgotPassword', guest: true }
  },
  // 工具相关
  {
    path: '/tools',
    name: 'Tools',
    component: () => import('@/views/tools/List.vue'),
    meta: { title: 'tools.title' }
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
  // 管理后台
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

// 路由守卫
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()

  // 设置页面标题
  document.title = `${to.meta.title || 'CPUModel'} - CPUModel`

  // 访客页面（已登录用户重定向到首页）
  if (to.meta.guest && userStore.isLoggedIn) {
    next('/')
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
    guest?: boolean
  }
}
