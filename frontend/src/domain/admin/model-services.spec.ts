import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { ModelService, ModelServiceCreateParams } from '@/types/models'
import {
  createDefaultModelServiceForm,
  createModelServiceEditForm,
  applyModelServicePreset,
  MODEL_SERVICE_PRESETS,
  normalizeModelServicePayload,
  normalizeModelServiceUpdatePayload
} from './model-services'

const modelService: ModelService = {
  id: 'svc-1',
  name: 'OpenAI Compatible',
  provider_type: 'openai_compatible',
  base_url: 'https://api.example.com/v1',
  model_name: 'gpt-test',
  is_default: true,
  is_enabled: true,
  timeout_seconds: 90,
  max_tokens: 4096,
  temperature: 0.3,
  has_api_key: true,
  api_key_masked: 'sk-***',
  last_test_status: 'success',
  last_test_message: 'ok',
  last_tested_at: '2026-08-05T00:00:00Z',
  created_at: '2026-08-04T00:00:00Z',
  updated_at: '2026-08-05T00:00:00Z'
}

test('模型服务默认表单使用平台约定的 openai compatible 默认值', () => {
  assert.deepEqual(createDefaultModelServiceForm(), {
    name: '',
    provider_type: 'openai_compatible',
    base_url: '',
    api_key: '',
    model_name: '',
    is_default: false,
    is_enabled: true,
    timeout_seconds: 60,
    max_tokens: 2048,
    temperature: 0.2
  })
})

test('模型服务编辑表单继承记录配置但不回填密钥明文', () => {
  assert.deepEqual(createModelServiceEditForm(modelService), {
    name: 'OpenAI Compatible',
    provider_type: 'openai_compatible',
    base_url: 'https://api.example.com/v1',
    api_key: '',
    model_name: 'gpt-test',
    is_default: true,
    is_enabled: true,
    timeout_seconds: 90,
    max_tokens: 4096,
    temperature: 0.3
  })
})

test('模型服务创建 payload 会修剪文本并移除 base url 尾部斜杠', () => {
  const form: ModelServiceCreateParams = {
    name: '  Custom Model  ',
    provider_type: 'openai_compatible',
    base_url: ' https://api.example.com/v1/// ',
    api_key: '  sk-test  ',
    model_name: '  gpt-test  ',
    is_default: false,
    is_enabled: true,
    timeout_seconds: 120,
    max_tokens: 8192,
    temperature: 0.7
  }

  assert.deepEqual(normalizeModelServicePayload(form), {
    name: 'Custom Model',
    provider_type: 'openai_compatible',
    base_url: 'https://api.example.com/v1',
    api_key: 'sk-test',
    model_name: 'gpt-test',
    is_default: false,
    is_enabled: true,
    timeout_seconds: 120,
    max_tokens: 8192,
    temperature: 0.7
  })
})

test('模型服务更新 payload 在密钥为空时不覆盖已有密钥', () => {
  const form: ModelServiceCreateParams = {
    name: ' Custom Model ',
    provider_type: 'openai_compatible',
    base_url: ' https://api.example.com/v1/ ',
    api_key: '   ',
    model_name: ' gpt-test ',
    is_default: true,
    is_enabled: true,
    timeout_seconds: 60,
    max_tokens: 2048,
    temperature: 0.2
  }

  const payload = normalizeModelServiceUpdatePayload(form)

  assert.equal('api_key' in payload, false)
  assert.equal(payload.base_url, 'https://api.example.com/v1')
  assert.equal(payload.name, 'Custom Model')
  assert.equal(payload.model_name, 'gpt-test')
})

test('模型服务预设会填充常用连接参数', () => {
  const form = createDefaultModelServiceForm()
  const preset = MODEL_SERVICE_PRESETS.find((item) => item.key === 'deepseek')
  assert.ok(preset)

  applyModelServicePreset(form, preset)

  assert.equal(form.name, 'DeepSeek')
  assert.equal(form.base_url, 'https://api.deepseek.com/v1')
  assert.equal(form.model_name, 'deepseek-chat')
  assert.equal(form.max_tokens, 4096)
  assert.equal(form.temperature, 0.2)
})
