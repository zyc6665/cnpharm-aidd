import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'

// 单测里不真跳：navigateToSso 被 mock，href 与调用参数都要可断言
const state = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  navigateToSso: vi.fn(),
  getSsoStatus: vi.fn(),
  replace: vi.fn(),
  info: vi.fn()
}))

vi.mock('@/utils/sso', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/sso')>()
  return { ...actual, navigateToSso: state.navigateToSso }
})

vi.mock('@/api/auth', () => ({ getSsoStatus: state.getSsoStatus }))

vi.mock('@/stores', () => ({ useUserStore: () => ({ login: vi.fn() }) }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
  useRoute: () => ({ path: '/login', query: state.query })
}))

vi.mock('ant-design-vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('ant-design-vue')>()
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: state.info }
  }
})

import Login from './Login.vue'

const AButton = {
  name: 'AButton',
  props: ['type', 'htmlType', 'href', 'block', 'size', 'loading'],
  emits: ['click'],
  template:
    '<button :data-variant="type" :href="href" @click="$emit(\'click\', $event)"><slot /></button>'
}

const AAlert = {
  name: 'AAlert',
  props: ['type', 'message', 'description', 'showIcon'],
  template: '<div data-testid="alert" :data-message="message" :data-description="description" />'
}

const AInput = {
  name: 'AInput',
  inheritAttrs: false,
  props: ['value'],
  emits: ['update:value'],
  template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
}

function mountLogin() {
  return mount(Login, {
    global: {
      plugins: [i18n],
      stubs: {
        AuthShell: { template: '<div><slot /></div>' },
        'a-form': {
          props: ['model', 'rules', 'layout'],
          emits: ['finish'],
          template: '<form @submit.prevent="$emit(\'finish\')"><slot /></form>'
        },
        'a-form-item': {
          props: ['label', 'name'],
          template: '<div class="form-item"><slot /></div>'
        },
        'a-input': AInput,
        'a-input-password': AInput,
        'a-checkbox': { props: ['checked'], template: '<label><slot /></label>' },
        'a-button': AButton,
        'a-alert': AAlert,
        'a-divider': { template: '<div class="divider"><slot /></div>' },
        UserOutlined: true,
        LockOutlined: true
      }
    }
  })
}

function localSubmitButton(wrapper: ReturnType<typeof mountLogin>) {
  const buttons = wrapper.findAll('form button')
  expect(buttons.length).toBe(1)
  return buttons[0]!
}

describe('Login.vue 统一认证接入', () => {
  beforeEach(() => {
    state.query = {}
    state.navigateToSso.mockReset()
    state.getSsoStatus.mockReset()
    state.replace.mockReset()
    state.info.mockReset()
  })

  it('启用时在表单上方给出主入口，href 带上编码后的 next', async () => {
    state.query = { redirect: '/tasks?page=2' }
    state.getSsoStatus.mockResolvedValue({
      enabled: true,
      authorize_path: '/api/v1/auth/sso/authorize',
      auto_provision: true
    })

    const wrapper = mountLogin()
    await flushPromises()

    const entry = wrapper.find('[data-testid="sso-login"]')
    expect(entry.exists()).toBe(true)
    expect(entry.attributes('href')).toBe(
      '/api/v1/auth/sso/authorize?next=%2Ftasks%3Fpage%3D2'
    )
    expect(entry.text()).toContain('使用统一身份认证登录')
    // 本地口令表单降级为次要入口
    expect(localSubmitButton(wrapper).attributes('data-variant')).toBe('default')
  })

  it('未启用时与改造前一致：没有入口、没有分隔线，本地按钮仍是主按钮', async () => {
    state.getSsoStatus.mockResolvedValue({
      enabled: false,
      authorize_path: '/api/v1/auth/sso/authorize',
      auto_provision: false
    })

    const wrapper = mountLogin()
    await flushPromises()

    expect(wrapper.find('[data-testid="sso-login"]').exists()).toBe(false)
    expect(wrapper.find('.divider').exists()).toBe(false)
    expect(wrapper.find('[data-testid="sso-error"]').exists()).toBe(false)
    expect(localSubmitButton(wrapper).attributes('data-variant')).toBe('primary')
  })

  it('?sso_error=conflict 显示对应文案并提示可用平台账号登录', async () => {
    state.query = { sso_error: 'conflict' }
    state.getSsoStatus.mockResolvedValue({ enabled: true, authorize_path: '', auto_provision: true })

    const wrapper = mountLogin()
    await flushPromises()

    const alert = wrapper.find('[data-testid="sso-error"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-message')).toBe('统一身份认证未完成')
    expect(alert.attributes('data-description')).toContain('该统一认证账号与平台已有账号冲突')
    expect(alert.attributes('data-description')).toContain('可改用平台账号登录')
  })

  it('未知错误码给通用文案，且状态探测失败也照样提示', async () => {
    state.query = { sso_error: 'weird' }
    state.getSsoStatus.mockResolvedValue(null)

    const wrapper = mountLogin()
    await flushPromises()

    const alert = wrapper.find('[data-testid="sso-error"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-description')).toContain('统一身份认证登录失败')
    // /status 失败不该顺手把入口也点亮
    expect(wrapper.find('[data-testid="sso-login"]').exists()).toBe(false)
  })

  it('点击入口调用 navigateToSso 而不是提交表单', async () => {
    state.getSsoStatus.mockResolvedValue({
      enabled: true,
      authorize_path: '/api/v1/auth/sso/authorize',
      auto_provision: true
    })

    const wrapper = mountLogin()
    await flushPromises()
    await wrapper.find('[data-testid="sso-login"]').trigger('click')

    expect(state.navigateToSso).toHaveBeenCalledTimes(1)
    expect(state.navigateToSso).toHaveBeenCalledWith(
      '/api/v1/auth/sso/authorize?next=%2Fworkspace'
    )
  })

  it('保留 ?sso_logout=1 的提示并清掉 query', async () => {
    state.query = { sso_logout: '1' }
    state.getSsoStatus.mockResolvedValue({
      enabled: true,
      authorize_path: '/api/v1/auth/sso/authorize',
      auto_provision: true
    })

    mountLogin()
    await flushPromises()

    expect(state.info).toHaveBeenCalledWith('已退出统一认证')
    expect(state.replace).toHaveBeenCalledWith({ path: '/login', query: {} })
  })
})
