import type { ModelService, ModelServiceCreateParams, ModelServiceUpdateParams } from '@/types/models'

export interface ModelServicePreset {
  key: string
  name: string
  base_url: string
  model_name: string
  max_tokens: number
  temperature: number
}

export const MODEL_SERVICE_PRESETS: ModelServicePreset[] = [
  { key: 'openai', name: 'OpenAI', base_url: 'https://api.openai.com/v1', model_name: 'gpt-4o-mini', max_tokens: 2048, temperature: 0.2 },
  { key: 'deepseek', name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model_name: 'deepseek-chat', max_tokens: 4096, temperature: 0.2 },
  { key: 'qwen', name: '通义千问 / DashScope', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model_name: 'qwen-plus', max_tokens: 4096, temperature: 0.2 },
  { key: 'ollama', name: 'Ollama（本地）', base_url: 'http://localhost:11434/v1', model_name: 'llama3.1', max_tokens: 2048, temperature: 0.2 }
]

export function applyModelServicePreset(
  form: ModelServiceCreateParams,
  preset: ModelServicePreset
): void {
  form.name = preset.name
  form.base_url = preset.base_url
  form.model_name = preset.model_name
  form.max_tokens = preset.max_tokens
  form.temperature = preset.temperature
}

export function createDefaultModelServiceForm(): ModelServiceCreateParams {
  return {
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
  }
}

export function createModelServiceEditForm(record: ModelService): ModelServiceCreateParams {
  return {
    name: record.name,
    provider_type: record.provider_type,
    base_url: record.base_url,
    api_key: '',
    model_name: record.model_name,
    is_default: record.is_default,
    is_enabled: record.is_enabled,
    timeout_seconds: record.timeout_seconds,
    max_tokens: record.max_tokens,
    temperature: record.temperature
  }
}

export function normalizeModelServicePayload(
  form: ModelServiceCreateParams
): ModelServiceCreateParams {
  return {
    name: form.name.trim(),
    provider_type: form.provider_type,
    base_url: form.base_url.trim().replace(/\/+$/, ''),
    api_key: form.api_key?.trim() || undefined,
    model_name: form.model_name.trim(),
    is_default: form.is_default,
    is_enabled: form.is_enabled,
    timeout_seconds: form.timeout_seconds,
    max_tokens: form.max_tokens,
    temperature: form.temperature
  }
}

export function normalizeModelServiceUpdatePayload(
  form: ModelServiceCreateParams
): ModelServiceUpdateParams {
  const payload: ModelServiceUpdateParams = normalizeModelServicePayload(form)
  if (!payload.api_key) {
    delete payload.api_key
  }
  return payload
}
