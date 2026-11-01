import { describe, it, expect } from 'vitest'
import type { AxiosError } from 'axios'
import type { ApiError } from '@/types/api'
import { buildErrorDisplayMessage } from './request'

const makeError = (status: number | undefined, data: unknown): AxiosError<ApiError> =>
  ({ response: status === undefined ? undefined : { status, data } }) as AxiosError<ApiError>

describe('buildErrorDisplayMessage', () => {
  it('展示字符串 detail 并截断过长内容', () => {
    const long = 'x'.repeat(500)
    const text = buildErrorDisplayMessage(makeError(400, { detail: long }))
    expect(text).toHaveLength(201)
    expect(text.endsWith('…')).toBe(true)
  })

  it('从 422 校验错误数组中取第一条 msg', () => {
    const text = buildErrorDisplayMessage(
      makeError(422, { detail: [{ loc: ['body', 'username'], msg: '用户名不能为空' }] })
    )
    expect(text).toBe('用户名不能为空')
  })

  it('5xx 无 detail 时使用通用文案，不泄露内部细节', () => {
    expect(buildErrorDisplayMessage(makeError(500, {}))).toBe('服务器内部错误，请稍后重试')
  })

  it('4xx 无 detail 时回退到通用文案', () => {
    expect(buildErrorDisplayMessage(makeError(400, {}))).toBe('请求失败')
  })

  it('detail 为对象时不渲染 [object Object]', () => {
    expect(buildErrorDisplayMessage(makeError(400, { detail: { nested: true } }))).toBe('请求失败')
  })
})
