import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  LEGACY_RESULT_VERSION,
  LEGACY_TOOL_PACKAGE_API_VERSION,
  RESULT_VERSION,
  TOOL_PACKAGE_API_VERSION,
  isResultVersion,
  isToolPackageApiVersion
} from './contract-versions'

test('tool package api version accepts new and legacy literals', () => {
  assert.equal(isToolPackageApiVersion(TOOL_PACKAGE_API_VERSION), true)
  assert.equal(isToolPackageApiVersion(LEGACY_TOOL_PACKAGE_API_VERSION), true)
  assert.equal(isToolPackageApiVersion('aidd.unknown/tool-package'), false)
  assert.equal(isToolPackageApiVersion(undefined), false)
})

test('result version accepts new and legacy literals', () => {
  assert.equal(isResultVersion(RESULT_VERSION), true)
  assert.equal(isResultVersion(LEGACY_RESULT_VERSION), true)
  assert.equal(isResultVersion('aidd.unknown/result'), false)
  assert.equal(isResultVersion(null), false)
})
