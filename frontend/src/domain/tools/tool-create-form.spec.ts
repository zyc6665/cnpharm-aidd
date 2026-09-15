import { describe, expect, it } from 'vitest'
import {
  buildTemplateExecutorConfig,
  buildToolTemplateFormPatch,
  createToolCreateFormState,
  createToolCreateSubmission,
  formatToolTemplateResourceText,
  toolConfigToCreateFormPatch,
  type ToolCreateEditorState,
} from './tool-create-form'

describe('tool create form domain', () => {
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
