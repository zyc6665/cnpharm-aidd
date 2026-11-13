import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'

const loginMock = vi.fn()

vi.mock('@/stores', () => ({
  useUserStore: () => ({ login: loginMock })
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} })
}))

// 登录页会探测统一认证状态，单测里必须挡掉真实请求（jsdom 没有后端）
vi.mock('@/api/auth', () => ({
  getSsoStatus: vi.fn().mockResolvedValue(null)
}))

vi.mock('ant-design-vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('ant-design-vue')>()
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  }
})

import Login from './Login.vue'

const AInput = {
  name: 'AInput',
  inheritAttrs: false,
  props: ['value'],
  emits: ['update:value'],
  template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
}

const AForm = {
  name: 'AForm',
  props: ['model', 'rules', 'layout'],
  emits: ['finish'],
  template: '<form @submit.prevent="$emit(\'finish\')"><slot /></form>'
}

function mountLogin() {
  return mount(Login, {
    global: {
      plugins: [i18n],
      stubs: {
        AuthShell: { template: '<div><slot /></div>' },
        'a-form': AForm,
        'a-form-item': {
          props: ['label', 'name'],
          template: '<div class="form-item"><span class="label">{{ label }}</span><slot /></div>'
        },
        'a-input': AInput,
        'a-input-password': AInput,
        'a-checkbox': { props: ['checked'], template: '<label><slot /></label>' },
        'a-button': { template: '<button type="submit"><slot /></button>' },
        UserOutlined: true,
        LockOutlined: true
      }
    }
  })
}

describe('Login.vue', () => {
  beforeEach(() => {
    loginMock.mockReset()
  })

  it('以账号（username）而非邮箱提交登录', async () => {
    const wrapper = mountLogin()
    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThanOrEqual(2)

    await inputs[0]!.setValue('alice')
    await inputs[1]!.setValue('s3cret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(loginMock).toHaveBeenCalledTimes(1)
    const submitted = loginMock.mock.calls[0]?.[0] as Record<string, unknown>
    expect(submitted.username).toBe('alice')
    expect(submitted.password).toBe('s3cret')
    expect(submitted).not.toHaveProperty('email')
  })

  it('标签为「账号」，不再显示注册/忘记密码入口', () => {
    const wrapper = mountLogin()
    const text = wrapper.text()
    expect(text).toContain('账号')
    expect(text).not.toContain('忘记密码')
    expect(text).not.toContain('立即注册')
  })
})
