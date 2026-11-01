import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  shouldAttemptTokenRefresh
} from '../src/api/auth-request-policy.ts'

test('登录/刷新/登出接口的 401 不应触发刷新会话', () => {
  assert.equal(shouldAttemptTokenRefresh('/auth/login'), false)
  assert.equal(shouldAttemptTokenRefresh('/auth/refresh'), false)
  assert.equal(shouldAttemptTokenRefresh('/auth/logout'), false)
  assert.equal(shouldAttemptTokenRefresh('http://127.0.0.1:8002/api/v1/auth/login'), false)
})

test('受保护接口仍应保留刷新会话能力', () => {
  assert.equal(shouldAttemptTokenRefresh('/users/me'), true)
  assert.equal(shouldAttemptTokenRefresh('/tasks'), true)
  assert.equal(shouldAttemptTokenRefresh('http://127.0.0.1:8002/api/v1/tasks/1'), true)
})

test('无 url 时默认允许尝试刷新', () => {
  assert.equal(shouldAttemptTokenRefresh(), true)
  assert.equal(shouldAttemptTokenRefresh(''), true)
})
