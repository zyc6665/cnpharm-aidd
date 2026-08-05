import type { ModelService, ModelServiceCreateParams, ModelServiceUpdateParams } from '@/types/models'

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
