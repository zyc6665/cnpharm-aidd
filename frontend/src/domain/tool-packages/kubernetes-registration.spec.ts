import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { KubernetesRegistrationOptions } from '@/types/tool-packages'
import {
  canPromoteKubernetesToolVersion,
  canRegisterKubernetesPackage,
  canSmokeKubernetesToolVersion,
  createDefaultKubernetesToolVersion,
  getKubernetesRegistrationVariants,
  parseKubernetesSmokeInput
} from './kubernetes-registration'

function options(
  overrides: Partial<KubernetesRegistrationOptions> = {}
): KubernetesRegistrationOptions {
  return {
    package_id: 'package-1',
    package_version_id: 'package-version-1',
    package_version: '1.2.3',
    manifest_digest: 'sha256:manifest',
    kubernetes_supported: true,
    image: 'registry.example/model:1.2.3',
    image_digest: `sha256:${'a'.repeat(64)}`,
    variants: [
      {
        name: 'gpu',
        accelerator: 'nvidia_cuda',
        entrypoint: ['runner.sh'],
        resources: { cpu: 4, memory_mb: 8192 }
      }
    ],
    resource_profiles: ['gpu-large'],
    tool_versions: [],
    existing_tool: null,
    ...overrides
  }
}

test('只展示具备 K8s executor 和不可变镜像摘要的变体', () => {
  const eligibleOptions = options()
  assert.equal(canRegisterKubernetesPackage(eligibleOptions), true)
  assert.deepEqual(getKubernetesRegistrationVariants(eligibleOptions), eligibleOptions.variants)

  assert.equal(
    canRegisterKubernetesPackage(options({ kubernetes_supported: false })),
    false
  )
  assert.deepEqual(
    getKubernetesRegistrationVariants(options({ image_digest: 'sha256:mutable' })),
    []
  )
})

test('根据包版本和 variant 生成不超过数据库限制的版本标签', () => {
  assert.equal(createDefaultKubernetesToolVersion('1.2.3', 'gpu'), '1.2.3-k8s-gpu')
  assert.equal(
    createDefaultKubernetesToolVersion('v'.repeat(60), 'nvidia-cuda').length,
    50
  )
})

test('只有符合运行状态的版本才能 smoke、提升或回切', () => {
  const candidate = {
    id: 'k8s-candidate',
    version: '1.0.0-k8s-cpu',
    executor_type: 'k8s_job',
    is_active: false,
    deprecated: false,
    smoke_status: null,
    smoke_task_id: null,
    smoke_created_at: null
  }
  assert.equal(canSmokeKubernetesToolVersion(candidate), true)
  assert.equal(canPromoteKubernetesToolVersion(candidate, 'ssh-current'), false)
  assert.equal(
    canPromoteKubernetesToolVersion({ ...candidate, smoke_status: 'FAILURE' }, 'ssh-current'),
    false
  )
  assert.equal(
    canPromoteKubernetesToolVersion({ ...candidate, smoke_status: 'SUCCESS' }, 'ssh-current'),
    true
  )
  assert.equal(
    canSmokeKubernetesToolVersion({ ...candidate, deprecated: true }),
    false
  )
  assert.equal(
    canPromoteKubernetesToolVersion({
      ...candidate,
      executor_type: 'ssh_job',
      is_active: true
    }, 'ssh-current'),
    true
  )
  assert.equal(
    canPromoteKubernetesToolVersion({ ...candidate, smoke_status: 'SUCCESS' }, candidate.id),
    false
  )
})

test('smoke 输入只接受 JSON 对象', () => {
  assert.deepEqual(
    parseKubernetesSmokeInput('{"params":{"seed":42},"file_ids":["file-1"]}'),
    { params: { seed: 42 }, file_ids: ['file-1'] }
  )
  assert.equal(parseKubernetesSmokeInput('[]'), null)
  assert.equal(parseKubernetesSmokeInput('{invalid'), null)
})
