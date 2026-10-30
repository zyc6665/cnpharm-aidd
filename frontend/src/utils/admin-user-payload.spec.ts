import { test } from 'vitest'
import assert from 'node:assert/strict'
import { buildAdminUserCreatePayload } from './admin-user-payload'

test('LDAP 用户创建请求不携带口令，且空邮箱不下发', () => {
  const payload = buildAdminUserCreatePayload({
    username: 'ldapuser',
    email: '',
    role: 'user',
    status: 'active',
    auth_source: 'ldap',
    password: 'should-not-send'
  })

  assert.equal('password' in payload, false)
  assert.equal(payload.email, undefined)
  assert.equal(payload.auth_source, 'ldap')
  assert.equal(payload.username, 'ldapuser')
})

test('本地用户创建请求携带口令，且账号去除首尾空白', () => {
  const payload = buildAdminUserCreatePayload({
    username: '  localuser  ',
    email: 'local@example.com',
    role: 'user',
    status: 'active',
    auth_source: 'local',
    password: 's3cret'
  })

  assert.equal(payload.username, 'localuser')
  assert.equal(payload.email, 'local@example.com')
  assert.equal(payload.password, 's3cret')
})
