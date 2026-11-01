import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('认证路由', () => {
  it('不再注册 /register 与 /forgot-password 路由', () => {
    const paths = router.getRoutes().map((route) => route.path)
    expect(paths).not.toContain('/register')
    expect(paths).not.toContain('/forgot-password')
  })

  it('不再存在 Register 与 ForgotPassword 命名路由', () => {
    const names = router.getRoutes().map((route) => route.name)
    expect(names).not.toContain('Register')
    expect(names).not.toContain('ForgotPassword')
  })

  it('登录路由仍然存在', () => {
    expect(router.getRoutes().some((route) => route.path === '/login')).toBe(true)
  })

  it('/admin 子页面解析后仍继承 requiresAdmin', () => {
    // 子路由自身只声明 title，权限由父路由 meta 在解析时合并；
    // 直接取 getRoutes() 的原始 meta 看不到继承结果，必须走 resolve()。
    for (const path of ['/admin/dashboard', '/admin/tools/1/edit', '/admin/audit']) {
      expect(router.resolve(path).meta.requiresAdmin, `${path} 未继承 requiresAdmin`).toBe(true)
    }
  })
})
