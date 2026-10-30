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
})
