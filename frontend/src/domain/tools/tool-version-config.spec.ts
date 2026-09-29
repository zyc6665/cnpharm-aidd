import { test } from 'vitest'
import assert from 'node:assert/strict'
import { buildToolVersionConfig } from './tool-version-config'

const inputSchema = { type: 'object', properties: { input: { type: 'string' } } }
const outputSchema = { type: 'object', properties: { result: { type: 'string' } } }

test('远程 API 工具版本 config 保留基础字段、文档、Agent 和 headers', () => {
  assert.deepEqual(
    buildToolVersionConfig({
      toolType: 'remote_api',
      timeoutSec: 3600,
      gpuRequired: false,
      inputSchema,
      outputSchema,
      documentationMarkdown: '  ## Usage  ',
      agentCapabilityConfig: { enabled: true, capability: 'general_tool' },
      apiEndpoint: 'https://api.example.com/predict',
      apiMethod: 'POST',
      apiHeaders: { Authorization: 'Bearer ${TOKEN}' }
    }),
    {
      type: 'remote_api',
      timeout_sec: 3600,
      gpu_required: false,
      input_schema: inputSchema,
      output_schema: outputSchema,
      documentation_markdown: '## Usage',
      agent_capability: { enabled: true, capability: 'general_tool' },
      endpoint: 'https://api.example.com/predict',
      method: 'POST',
      headers: { Authorization: 'Bearer ${TOKEN}' }
    }
  )
})

test('Docker 工具版本 config 只在命令和环境变量非空时写入可选字段', () => {
  assert.deepEqual(
    buildToolVersionConfig({
      toolType: 'docker_image',
      timeoutSec: 600,
      gpuRequired: true,
      gpuMemoryMb: 24576,
      inputSchema,
      outputSchema,
      dockerImage: 'molp-pc:latest',
      dockerCommand: ['/app/run.py', '--batch-size', '8'],
      dockerEnv: { MODEL_DIR: '/models' }
    }),
    {
      type: 'docker_image',
      timeout_sec: 600,
      gpu_required: true,
      input_schema: inputSchema,
      output_schema: outputSchema,
      gpu_memory_mb: 24576,
      image: 'molp-pc:latest',
      command: ['/app/run.py', '--batch-size', '8'],
      env: { MODEL_DIR: '/models' }
    }
  )

  assert.equal(
    'command' in
      buildToolVersionConfig({
        toolType: 'docker_image',
        timeoutSec: 600,
        gpuRequired: false,
        inputSchema,
        outputSchema,
        dockerImage: 'molp-pc:latest',
        dockerCommand: [],
        dockerEnv: {}
      }),
    false
  )
})

test('Python 脚本工具版本 config 只在参数非空时写入 args', () => {
  assert.deepEqual(
    buildToolVersionConfig({
      toolType: 'python_script',
      timeoutSec: 900,
      gpuRequired: false,
      inputSchema,
      outputSchema,
      pythonScript: '/app/predict.py',
      pythonArguments: ['--device', 'cpu']
    }),
    {
      type: 'python_script',
      timeout_sec: 900,
      gpu_required: false,
      input_schema: inputSchema,
      output_schema: outputSchema,
      script_path: '/app/predict.py',
      args: ['--device', 'cpu']
    }
  )
})

test('SSH 工具版本 config 保留认证、docker_exec 容器字段和输出文件规则', () => {
  assert.deepEqual(
    buildToolVersionConfig({
      toolType: 'ssh_job',
      timeoutSec: 7200,
      gpuRequired: true,
      inputSchema,
      outputSchema,
      sshHost: '10.202.2.228',
      sshPort: 22,
      sshUsername: 'runner',
      sshAuthType: 'key',
      sshAuthRef: 'ssh_kaiwu',
      sshPasswordRef: 'ignored_password',
      sshRunnerMode: 'docker_exec',
      sshRemoteBaseDir: '/srv/platform-jobs',
      sshContainerBaseDir: '/workspace/platform-jobs',
      sshEntrypoint: '/app/platform_run.sh',
      sshContainerName: 'kaiwu',
      sshDevice: 'cuda:0',
      sshCleanupRemote: true,
      sshStrictHostKeyChecking: false,
      sshEnv: { CUDA_VISIBLE_DEVICES: '0' },
      sshOutputGlobs: ['output/result.json', 'output/artifacts/**/*']
    }),
    {
      type: 'ssh_job',
      timeout_sec: 7200,
      gpu_required: true,
      input_schema: inputSchema,
      output_schema: outputSchema,
      host: '10.202.2.228',
      port: 22,
      username: 'runner',
      auth_type: 'key',
      auth_ref: 'ssh_kaiwu',
      runner_mode: 'docker_exec',
      remote_base_dir: '/srv/platform-jobs',
      entrypoint: '/app/platform_run.sh',
      cleanup_remote: true,
      strict_host_key_checking: false,
      container_name: 'kaiwu',
      container_base_dir: '/workspace/platform-jobs',
      device: 'cuda:0',
      env: { CUDA_VISIBLE_DEVICES: '0' },
      output_globs: ['output/result.json', 'output/artifacts/**/*']
    }
  )
})

test('SSH shell/password 模式不写入 docker 容器字段并使用 password_ref', () => {
  const config = buildToolVersionConfig({
    toolType: 'ssh_job',
    timeoutSec: 7200,
    gpuRequired: false,
    inputSchema,
    outputSchema,
    sshHost: 'node-1',
    sshPort: 2222,
    sshUsername: 'runner',
    sshAuthType: 'password',
    sshAuthRef: 'ignored_key',
    sshPasswordRef: 'ssh_password',
    sshRunnerMode: 'shell',
    sshRemoteBaseDir: '/srv/jobs',
    sshContainerBaseDir: '/container/jobs',
    sshEntrypoint: '/srv/model/platform_run.sh',
    sshContainerName: 'ignored-container',
    sshDevice: '',
    sshCleanupRemote: false,
    sshStrictHostKeyChecking: true,
    sshEnv: {},
    sshOutputGlobs: []
  })

  assert.equal(config.password_ref, 'ssh_password')
  assert.equal('auth_ref' in config, false)
  assert.equal('container_name' in config, false)
  assert.equal('container_base_dir' in config, false)
  assert.equal('output_globs' in config, false)
})

test('Tool Package v2 manifest 与实际执行器配置共存', () => {
  const manifest = { api_version: 'aidd.sciminer/tool-package.v2', kind: 'ToolPackage' }
  const config = buildToolVersionConfig({
    toolType: 'ssh_job',
    timeoutSec: 3600,
    gpuRequired: false,
    inputSchema,
    outputSchema,
    toolPackageManifest: manifest,
    sshHost: 'runner-1',
    sshUsername: 'model',
    sshAuthType: 'key',
    sshAuthRef: 'ssh_model',
    sshRunnerMode: 'shell',
    sshRemoteBaseDir: '/srv/jobs',
    sshEntrypoint: '/app/platform_run.sh',
    sshCleanupRemote: true,
    sshStrictHostKeyChecking: true,
  })

  assert.deepEqual(config.tool_package_manifest, manifest)
  assert.equal(config.type, 'ssh_job')
})

test('Kubernetes Job 工具版本 config 只保存受控运行时引用', () => {
  assert.deepEqual(
    buildToolVersionConfig({
      toolType: 'k8s_job',
      timeoutSec: 14400,
      gpuRequired: true,
      inputSchema,
      outputSchema,
      k8sImage: 'registry.example/model@sha256:abc',
      k8sResourceProfile: 'gpu-large',
    }),
    {
      type: 'k8s_job',
      timeout_sec: 14400,
      gpu_required: true,
      input_schema: inputSchema,
      output_schema: outputSchema,
      runtime: { image: 'registry.example/model@sha256:abc' },
      resource_profile: 'gpu-large',
    }
  )
})
