import { describe, expect, it } from 'vitest'
import {
  buildRemoteToolRegistrationPayload,
  buildTemplateExecutorConfig,
  buildToolEditFormPatch,
  buildToolTemplateFormPatch,
  buildToolAgentCapabilityEnablePatch,
  createToolCreateFormState,
  createToolCreateSubmission,
  formatToolCreateSubmissionErrorMessage,
  formatToolTemplateResourceText,
  remoteToolStageStatusDisplay,
  resolveToolCreateSubmissionBlocker,
  toolConfigToCreateFormPatch,
  type ToolCreateEditorState,
} from './tool-create-form'

describe('tool create form domain', () => {
  it('formats remote tool registration stage status display', () => {
    expect(remoteToolStageStatusDisplay('success')).toEqual({ color: 'green', text: '成功' })
    expect(remoteToolStageStatusDisplay('warning')).toEqual({ color: 'orange', text: '警告' })
    expect(remoteToolStageStatusDisplay('failure')).toEqual({ color: 'red', text: '失败' })
  })

  it('formats tool create submission parse errors', () => {
    expect(formatToolCreateSubmissionErrorMessage(new Error('配置键不能为空'))).toBe('配置键不能为空')
    expect(formatToolCreateSubmissionErrorMessage(new Error('Unexpected token'))).toBe('JSON 格式错误，请检查配置')
    expect(formatToolCreateSubmissionErrorMessage('bad json')).toBe('JSON 格式错误，请检查配置')
  })

  it('builds an agent capability enable patch without overwriting existing rows', () => {
    const emptyState = createToolCreateFormState()
    emptyState.agent_stage = ''

    expect(buildToolAgentCapabilityEnablePatch(emptyState)).toMatchObject({
      agent_inputs: [{ semantic_type: '', field: '', accepted_extensions: '' }],
      agent_outputs: [
        {
          semantic_type: '',
          source: 'output_files',
          path: '',
          match_extension: '',
          filename_contains_any: '',
          required: true,
        },
      ],
      agent_stage: 'molecule_generation',
    })

    const populatedState = createToolCreateFormState()
    populatedState.agent_stage = 'custom_stage'
    populatedState.agent_inputs = [{ semantic_type: 'protein_structure@1', field: 'protein', accepted_extensions: '.pdb' }]
    populatedState.agent_outputs = [
      {
        semantic_type: 'binding_pocket@1',
        source: 'output_files',
        path: 'output/pocket.pdb',
        match_extension: '.pdb',
        filename_contains_any: 'pocket',
        required: true,
      },
    ]

    expect(buildToolAgentCapabilityEnablePatch(populatedState)).toEqual({})
  })

  it('resolves submission blocker messages before API calls', () => {
    expect(resolveToolCreateSubmissionBlocker({
      submission: { agentCapabilityComplete: false, versionConfigChanged: false },
      version: '1.0.0',
      originalVersion: '1.0.0',
    })).toBe('Agent 编排能力需要填写能力、至少一个输入和至少一个输出')

    expect(resolveToolCreateSubmissionBlocker({
      submission: { agentCapabilityComplete: true, versionConfigChanged: true },
      version: '1.0.0',
      originalVersion: '1.0.0',
    })).toBe('修改版本配置时请填写新的版本号')

    expect(resolveToolCreateSubmissionBlocker({
      submission: { agentCapabilityComplete: true, versionConfigChanged: true },
      version: '1.0.1',
      originalVersion: '1.0.0',
    })).toBeNull()
  })

  it('builds remote self-registration payload from create form state', () => {
    const formState = createToolCreateFormState()
    formState.remote_base_url = '  https://model.example.com  '
    formState.category_id = 'cat-1'
    formState.remote_run_smoke_test = false
    formState.remote_publish_on_success = true
    formState.icon = ''
    formState.icon_url = 'https://cdn.example.com/icon.png'
    formState.is_public = false
    formState.timeout_sec = 1800

    expect(buildRemoteToolRegistrationPayload(formState)).toEqual({
      base_url: 'https://model.example.com',
      category_id: 'cat-1',
      run_smoke_test: false,
      publish_on_success: false,
      icon: undefined,
      icon_url: 'https://cdn.example.com/icon.png',
      is_public: false,
      timeout_sec: 1800,
    })
  })

  it('builds an edit-form patch from an existing tool detail', () => {
    const config = {
      type: 'ssh_job',
      host: 'gpu-host',
      port: 2222,
      username: 'runner',
      auth_type: 'key',
      auth_ref: 'secret/key',
      runner_mode: 'shell',
      remote_base_dir: '/opt/aidd',
      entrypoint: './run.sh',
      env: { CUDA_VISIBLE_DEVICES: '0' },
      output_globs: ['output/result.json'],
      input_schema: { type: 'object', properties: { protein_pdb: { type: 'file' } } },
      output_schema: { type: 'object' },
    }

    const patch = buildToolEditFormPatch({
      id: 'tool-1',
      name: 'LVpocket',
      slug: 'lvpocket-pocket-prediction',
      description: 'Predict pockets',
      category: 'AIDD',
      category_id: 'cat-1',
      tags: [{ id: 'tag-1', name: 'Pocket', color: '#1677ff', sort_order: 1 }],
      status: 'published',
      usage_count: 0,
      view_count: 0,
      favorite_count: 0,
      is_public: true,
      gpu_required: true,
      gpu_memory_mb: 8192,
      timeout_sec: 7200,
      icon: 'ExperimentOutlined',
      icon_url: '',
      created_at: '2026-09-15T00:00:00Z',
      current_version: {
        id: 'version-1',
        tool_id: 'tool-1',
        version: '2.0.0',
        changelog: 'Updated model',
        notes: 'Keep CUDA image warm',
        config,
        is_active: true,
        deprecated: false,
      },
    })

    expect(patch.form).toMatchObject({
      name: 'LVpocket',
      slug: 'lvpocket-pocket-prediction',
      description: 'Predict pockets',
      category_id: 'cat-1',
      tag_ids: ['tag-1'],
      gpu_required: true,
      gpu_memory_mb: 8192,
      timeout_sec: 7200,
      version: '2.0.0',
      changelog: 'Updated model',
      notes: 'Keep CUDA image warm',
      tool_type: 'ssh_job',
      ssh_host: 'gpu-host',
      ssh_runner_mode: 'shell',
    })
    expect(patch.editor.sshEnvEntries).toEqual([{ key: 'CUDA_VISIBLE_DEVICES', value: '0' }])
    expect(patch.editor.sshOutputGlobItems).toEqual(['output/result.json'])
    expect(patch.originalVersion).toBe('2.0.0')
    expect(patch.originalChangelog).toBe('Updated model')
    expect(patch.originalNotes).toBe('Keep CUDA image warm')
    expect(patch.originalConfigSnapshot).toContain('ssh_job')
  })

  it('builds a create-form patch from a tool template summary', () => {
    const patch = buildToolTemplateFormPatch({
      currentToolType: 'remote_api',
      template: {
        name: 'LVpocket',
        slug: 'lvpocket-pocket-prediction',
        description: 'Predict binding pockets',
        version: '2.0.0',
        capability: 'pocket_prediction',
        stage: 'pocket_prediction',
        executor_types: ['ssh_job'],
        inputs: [
          {
            semantic_type: 'protein_structure@1',
            field: 'protein_pdb',
            accepted_extensions: ['.pdb'],
          },
        ],
        outputs: [
          {
            semantic_type: 'binding_pocket@1',
            source: 'output_files',
            path: 'output/pockets.pdb',
            required: true,
          },
        ],
        resource_profile: {
          gpu_required: true,
          gpu_memory_gb: 8,
          timeout_minutes: 2000,
        },
      },
    })

    expect(patch.form).toMatchObject({
      tool_type: 'ssh_job',
      name: 'LVpocket',
      slug: 'lvpocket-pocket-prediction',
      description: 'Predict binding pockets',
      version: '2.0.0',
      agent_capability_enabled: true,
      agent_capability: 'pocket_prediction',
      agent_stage: 'pocket_prediction',
      gpu_required: true,
      gpu_memory_mb: 8192,
      timeout_sec: 86400,
    })
    expect(patch.form.agent_inputs).toEqual([
      {
        semantic_type: 'protein_structure@1',
        field: 'protein_pdb',
        accepted_extensions: '.pdb',
      },
    ])
    expect(patch.form.agent_outputs).toEqual([
      {
        semantic_type: 'binding_pocket@1',
        source: 'output_files',
        path: 'output/pockets.pdb',
        match_extension: '',
        filename_contains_any: '',
        required: true,
      },
    ])
    expect(patch.agentDefaultsText).toBe('{}')
  })

  it('forces manual remote registration when a remote template is selected', () => {
    const patch = buildToolTemplateFormPatch({
      currentToolType: 'remote_api',
      template: {
        name: 'Remote Scorer',
        slug: 'remote-scorer',
        description: 'Score molecules',
        version: '1.0.0',
        capability: 'property_prediction',
        stage: 'property_prediction',
        executor_types: ['remote_api'],
        inputs: [],
        outputs: [],
        resource_profile: { gpu_required: false, timeout_minutes: 5 },
      },
    })

    expect(patch.form.tool_type).toBeUndefined()
    expect(patch.form.remote_api_registration_mode).toBe('manual')
    expect(patch.form.timeout_sec).toBe(300)
  })

  it('formats template resource profile text for display', () => {
    expect(formatToolTemplateResourceText({
      tier: 'gpu-small',
      cpu: 8,
      memory_gb: 32,
      expected_minutes: 20,
      timeout_minutes: 60,
      gpu_required: true,
      gpu_memory_gb: 12,
    })).toBe('gpu-small · GPU 12GB · CPU 8 · MEM 32GB · 20/60 min')

    expect(formatToolTemplateResourceText(undefined)).toBe('')
  })

  it('builds ssh template executor config from normalized editor state', () => {
    const formState = createToolCreateFormState()
    formState.tool_type = 'ssh_job'
    formState.ssh_host = 'gpu-host'
    formState.ssh_port = 2222
    formState.ssh_username = 'runner'
    formState.ssh_auth_type = 'password'
    formState.ssh_password_ref = 'secret/password'
    formState.ssh_runner_mode = 'docker_exec'
    formState.ssh_container_name = 'aidd-worker'
    formState.ssh_container_base_dir = '/workspace'
    formState.ssh_entrypoint = './run.sh'
    formState.ssh_device = 'cuda:0'

    const editorState: ToolCreateEditorState = {
      apiHeaderEntries: [],
      dockerCommandItems: [],
      dockerEnvEntries: [],
      pythonArgumentItems: [],
      sshEnvEntries: [{ key: 'CUDA_VISIBLE_DEVICES', value: '0' }],
      sshOutputGlobItems: [' output/result.json ', '', 'output/artifacts/**/*'],
    }

    expect(buildTemplateExecutorConfig(formState, editorState)).toEqual({
      host: 'gpu-host',
      port: 2222,
      username: 'runner',
      auth_type: 'password',
      password_ref: 'secret/password',
      runner_mode: 'docker_exec',
      remote_base_dir: '',
      entrypoint: './run.sh',
      cleanup_remote: true,
      strict_host_key_checking: true,
      container_name: 'aidd-worker',
      container_base_dir: '/workspace',
      device: 'cuda:0',
      env: { CUDA_VISIBLE_DEVICES: '0' },
      output_globs: ['output/result.json', 'output/artifacts/**/*'],
    })
  })

  it('returns a pure create submission with parsed schemas and initial version', () => {
    const formState = createToolCreateFormState()
    formState.name = 'Docking'
    formState.slug = 'vina-docking'
    formState.category_id = 'cat-1'
    formState.tool_type = 'docker_image'
    formState.docker_image = 'aidd/vina:latest'
    formState.input_schema = '{"type":"object","properties":{"ligand":{"type":"file"}}}'
    formState.output_schema = '{"type":"object"}'
    formState.documentation_markdown = '  # Docking  '
    formState.tag_ids = ['tag-1']

    const submission = createToolCreateSubmission({
      formState,
      editorState: {
        apiHeaderEntries: [],
        dockerCommandItems: [' run ', '', '--score'],
        dockerEnvEntries: [{ key: 'OMP_NUM_THREADS', value: '4' }],
        pythonArgumentItems: [],
        sshEnvEntries: [],
        sshOutputGlobItems: [],
      },
      agentDefaultsText: '{}',
      isEdit: false,
      originalVersion: '',
      originalChangelog: '',
      originalNotes: '',
      originalConfigSnapshot: '',
    })

    expect(submission.agentCapabilityComplete).toBe(true)
    expect(submission.versionConfigChanged).toBe(false)
    expect(submission.data.initial_version).toMatchObject({
      version: '1.0.0',
      config: {
        type: 'docker_image',
        image: 'aidd/vina:latest',
        command: ['run', '--score'],
        env: { OMP_NUM_THREADS: '4' },
        documentation_markdown: '# Docking',
      },
    })
    expect(submission.data.tag_ids).toEqual(['tag-1'])
  })

  it('converts existing tool config into form and editor patches', () => {
    const patch = toolConfigToCreateFormPatch({
      type: 'ssh_job',
      host: 'host-1',
      port: 2022,
      username: 'alice',
      auth_type: 'key',
      auth_ref: 'secret/key',
      runner_mode: 'shell',
      remote_base_dir: '/opt/aidd',
      entrypoint: 'python run.py',
      cleanup_remote: false,
      strict_host_key_checking: false,
      env: { A: '1' },
      output_globs: ['output/result.json'],
      input_schema: { type: 'object', properties: { protein: { type: 'file' } } },
      output_schema: { type: 'object' },
      agent_capability: {
        enabled: true,
        capability: 'pocket_prediction',
        inputs: [{ semantic_type: 'protein_structure@1', field: 'protein' }],
        outputs: [{ semantic_type: 'pocket_structure@1', source: 'output_files', required: true }],
      },
    })

    expect(patch.form.tool_type).toBe('ssh_job')
    expect(patch.form.ssh_host).toBe('host-1')
    expect(patch.form.ssh_runner_mode).toBe('shell')
    expect(patch.form.ssh_cleanup_remote).toBe(false)
    expect(patch.form.input_schema).toContain('protein')
    expect(patch.form.agent_capability_enabled).toBe(true)
    expect(patch.editor.sshEnvEntries).toEqual([{ key: 'A', value: '1' }])
    expect(patch.editor.sshOutputGlobItems).toEqual(['output/result.json'])
  })
})
