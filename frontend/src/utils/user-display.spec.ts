import { test } from 'vitest'
import assert from 'node:assert/strict'
import { formatUserEmail, getUserDisplayName } from './user-display'

test('email 为 null 时展示名回退到账号名', () => {
  assert.equal(
    getUserDisplayName({ username: 'alice', email: null }),
    'alice'
  )
})

test('email 为 null 时邮箱列回退为「—」，不显示 null', () => {
  assert.equal(formatUserEmail(null), '-')
  assert.equal(formatUserEmail(undefined), '-')
  assert.equal(formatUserEmail(''), '-')
})

test('既无账号也无邮箱时不报错，返回空字符串', () => {
  assert.equal(getUserDisplayName({ username: '', email: null }), '')
})

test('有邮箱且无展示名/账号时回退邮箱前缀', () => {
  assert.equal(
    getUserDisplayName({ username: '', email: 'bob@example.com' }),
    'bob'
  )
})

test('展示名优先于账号名，邮箱原样展示', () => {
  assert.equal(
    getUserDisplayName({ display_name: '爱丽丝', username: 'alice', email: null }),
    '爱丽丝'
  )
  assert.equal(formatUserEmail('a@b.com'), 'a@b.com')
})
