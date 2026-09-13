import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务详情页应使用统一页头承载标题和主要操作', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('AppPageHeader'), true)
  assert.equal(source.includes(':title="detailTitle"'), true)
  assert.equal(source.includes(':subtitle="detailSubtitle"'), true)
  assert.equal(source.includes('task-detail-actions'), true)
  assert.equal(source.includes('<a-space class="task-detail-actions" wrap>'), true)
})

test('任务详情页状态卡和侧栏应优化移动端可读性', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes('status-label'), true)
  assert.equal(source.includes('status-line'), true)
  assert.equal(source.includes('word-break: break-all'), true)
  assert.equal(source.includes('position: sticky'), true)
})

test('任务详情页不应展示运行时长或总时长文案', () => {
  const source = readSource('src/views/tasks/Detail.vue')

  assert.equal(source.includes("t('tasks.runningTime')"), false)
  assert.equal(source.includes("t('tasks.duration')"), false)
  assert.equal(source.includes('timeline-duration'), false)
  assert.equal(source.includes('calculateDuration('), false)
})

test('MSIGN 工具页应为 ligand_pdb 提供上传 SDF 转 PDB 辅助入口', () => {
  const source = readSource('src/views/tools/Detail.vue')
  const domainSource = readSource('src/domain/tools/detail-file-inputs.ts')
  const filesApiSource = readSource('src/api/files.ts')

  assert.equal(source.includes('showSdfToPdbConverter'), true)
  assert.equal(source.includes('shouldShowSdfToPdbConverter'), true)
  assert.equal(domainSource.includes("toolSlug === SDF_TO_PDB_TOOL_SLUG"), true)
  assert.equal(domainSource.includes("key === 'ligand_pdb' || key.endsWith('.ligand_pdb')"), true)
  assert.equal(source.includes('handleSdfToPdbConversion'), true)
  assert.equal(source.includes(':get-file-accept="getFileAccept"'), true)
  assert.equal(filesApiSource.includes('convertSdfToPdb'), true)
})

test('SDF 转 PDB 后应同步文件显示和表单校验字段', () => {
  const source = readSource('src/views/tools/Detail.vue')
  const domainSource = readSource('src/domain/tools/detail-file-inputs.ts')
  const formSource = readSource('src/composables/useToolDetailRunForm.ts')

  assert.equal(source.includes('getToolFileAccept'), true)
  assert.equal(domainSource.includes("tokens.add('.sdf')"), true)
  assert.equal(source.includes("filename.toLowerCase().endsWith('.sdf')"), true)
  assert.equal(source.includes('void handleSdfToPdbConversion(key, rawFile)'), true)
  assert.equal(source.includes('createConvertedUploadFile'), true)
  assert.equal(source.includes('fileList[key] = [createConvertedUploadFile(res.data)]'), true)
  assert.equal(source.includes('formState[key] = res.data.id'), true)
  assert.equal(formSource.includes('sdfConversionLoading[key] ||'), true)
  assert.equal(source.includes('clearFieldValidation(key)'), true)
  assert.equal(source.includes('sdfConversionStatusText'), true)
  assert.equal(source.includes('getToolRequestErrorMessage'), true)
  assert.equal(domainSource.includes('SDF 转 PDB 失败，请检查文件格式或后端转换服务'), true)
})
