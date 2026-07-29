import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  buildTaskSubmissionPayload,
  flattenToolInputSchema
} from '../src/views/tools/detail-schema.ts'

const gcdmSchema = {
  type: 'object',
  properties: {
    task_id: {
      type: 'string',
      description: '平台任务 ID',
      hidden: true
    },
    task_name: {
      type: 'string',
      description: '模型侧能力名称，固定为 pocket_generation',
      default: 'pocket_generation',
      hidden: true
    },
    params: {
      type: 'object',
      properties: {
        n_samples: {
          type: 'integer',
          description: '希望生成的候选分子数量',
          default: 8,
          minimum: 1
        },
        device: {
          type: ['string', 'null'],
          description: '运行设备，例如 cuda:0 或 cpu',
          default: 'cuda:0'
        }
      }
    },
    input_files: {
      type: 'object',
      properties: {
        pocket_pdb: {
          type: 'string',
          description: '已裁剪 pocket PDB 的任务内相对路径，例如 input/pocket.pdb'
        }
      },
      required: ['pocket_pdb']
    }
  },
  required: ['task_id', 'params', 'input_files']
} as const

const molpPcSchema = {
  type: 'object',
  properties: {
    smiles_csv: {
      type: 'string',
      format: 'file',
      title: 'SMILES CSV 文件',
      description: '上传包含 SMILES 列的 CSV 文件'
    },
    device: {
      type: 'string',
      default: 'cpu'
    }
  },
  required: ['smiles_csv']
} as const

const peptideSequenceSchema = {
  type: 'object',
  properties: {
    sequences: {
      type: ['array', 'string'],
      title: 'Peptide sequence',
      description: 'One or more peptide sequences using canonical amino-acid letters.',
      items: {
        type: 'string'
      }
    }
  }
} as const

test('工具详情 schema 适配应隐藏平台内部字段并正确归一化文件与数字类型', () => {
  const flattened = flattenToolInputSchema(gcdmSchema as never)

  assert.notEqual(flattened, undefined)
  assert.equal(flattened?.properties.task_id, undefined)
  assert.equal(flattened?.properties.task_name, undefined)
  assert.equal(flattened?.properties['input_files.pocket_pdb']?.type, 'file')
  assert.equal(flattened?.properties['params.n_samples']?.type, 'number')
  assert.equal(flattened?.properties['params.device']?.type, 'string')
  assert.equal(flattened?.properties['input_files.pocket_pdb']?.title, 'Pocket Pdb')
  assert.deepEqual(flattened?.required, ['input_files.pocket_pdb'])
})

test('ssh_job 提交参数应将上传文件映射为任务内相对路径', () => {
  const flattened = flattenToolInputSchema(gcdmSchema as never)

  const payload = buildTaskSubmissionPayload({
    flattenedSchema: flattened!,
    formState: {
      'params.n_samples': 8,
      'params.device': 'cuda:0'
    },
    uploadedFiles: {
      'input_files.pocket_pdb': {
        fileId: 'file-1',
        filename: 'pocket.pdb',
        downloadUrl: '/api/v1/files/file-1/download'
      }
    },
    executorType: 'ssh_job'
  })

  assert.deepEqual(payload, {
    params: {
      params: {
        n_samples: 8,
        device: 'cuda:0'
      },
      input_files: {
        pocket_pdb: 'input/pocket.pdb'
      }
    },
    fileIds: ['file-1']
  })
})

test('remote_api 提交参数应继续向 input_files 写入可下载 URL', () => {
  const flattened = flattenToolInputSchema(gcdmSchema as never)

  const payload = buildTaskSubmissionPayload({
    flattenedSchema: flattened!,
    formState: {},
    uploadedFiles: {
      'input_files.pocket_pdb': {
        fileId: 'file-2',
        filename: 'pocket.pdb',
        downloadUrl: '/api/v1/files/file-2/download'
      }
    },
    executorType: 'remote_api'
  })

  assert.deepEqual(payload, {
    params: {
      input_files: {
        pocket_pdb: '/api/v1/files/file-2/download'
      }
    },
    fileIds: ['file-2']
  })
})

test('顶层 format=file 字段应归一化为文件上传字段', () => {
  const flattened = flattenToolInputSchema(molpPcSchema as never)

  assert.notEqual(flattened, undefined)
  assert.equal(flattened?.properties.smiles_csv?.type, 'file')
  assert.deepEqual(flattened?.required, ['smiles_csv'])
})

test('ssh_job 顶层文件字段应拆分为 params 和 input_files', () => {
  const flattened = flattenToolInputSchema(molpPcSchema as never)

  const payload = buildTaskSubmissionPayload({
    flattenedSchema: flattened!,
    formState: {
      device: 'cpu'
    },
    uploadedFiles: {
      smiles_csv: {
        fileId: 'file-3',
        filename: 'smiles.csv',
        downloadUrl: '/api/v1/files/file-3/download'
      }
    },
    executorType: 'ssh_job'
  })

  assert.deepEqual(payload, {
    params: {
      params: {
        device: 'cpu'
      },
      input_files: {
        smiles_csv: 'input/smiles.csv'
      }
    },
    fileIds: ['file-3']
  })
})

test('字符串数组联合类型肽序列字段应归一化为多行文本输入', () => {
  const flattened = flattenToolInputSchema(peptideSequenceSchema as never)

  assert.notEqual(flattened, undefined)
  assert.equal(flattened?.properties.sequences?.type, 'string')
  assert.equal(flattened?.properties.sequences?.format, 'textarea')
})
