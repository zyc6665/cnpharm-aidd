import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  buildRefreshTokenRequestConfig,
  shouldAttachAuthHeader,
  shouldAttemptTokenRefresh
} from '../src/api/auth-request-policy.ts'

test('登录接口不应附带旧的认证头', () => {
  assert.equal(shouldAttachAuthHeader('/auth/login'), false)
  assert.equal(shouldAttachAuthHeader('http://127.0.0.1:8002/api/v1/auth/login'), false)
})

test('登录和刷新接口的 401 不应触发刷新令牌', () => {
  assert.equal(shouldAttemptTokenRefresh('/auth/login'), false)
  assert.equal(shouldAttemptTokenRefresh('/auth/refresh'), false)
})

test('受保护接口仍应保留认证和刷新能力', () => {
  assert.equal(shouldAttachAuthHeader('/users/me'), true)
  assert.equal(shouldAttemptTokenRefresh('/tasks'), true)
})

test('刷新令牌请求应使用 query 参数', () => {
  assert.deepEqual(buildRefreshTokenRequestConfig('refresh-token'), {
    params: {
      refresh_token: 'refresh-token'
    }
  })
})
