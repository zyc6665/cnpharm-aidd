import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildTaskFailureAdvice,
  buildTaskFailureDiagnostics,
  formatTaskDetailTime,
  formatTaskFileSize,
  formatTaskRunningDuration,
  formatWaitSeconds,
  getTaskCompletedTitleKey,
  parseTaskProgressDetail,
  readTaskQueueInfo
} from './detail'

test('任务详情时间格式保持页面展示格式', () => {
  assert.equal(formatTaskDetailTime('2026-08-05T02:30:00Z'), '2026-08-05 02:30:00')
})

test('任务详情文件大小格式支持空值、B、KB、MB 和 GB', () => {
  assert.equal(formatTaskFileSize(undefined), '0 B')
  assert.equal(formatTaskFileSize(0), '0 B')
  assert.equal(formatTaskFileSize(512), '512 B')
  assert.equal(formatTaskFileSize(1536), '1.5 KB')
  assert.equal(formatTaskFileSize(1024 * 1024), '1 MB')
  assert.equal(formatTaskFileSize(1024 * 1024 * 1024), '1 GB')
})

test('任务运行时长格式支持秒、分钟和小时', () => {
  assert.equal(
    formatTaskRunningDuration('2026-08-05T06:00:00Z', '2026-08-05T06:00:45Z'),
    '45s'
  )
  assert.equal(
    formatTaskRunningDuration('2026-08-05T06:00:00Z', '2026-08-05T06:02:05Z'),
    '2m 5s'
  )
  assert.equal(
    formatTaskRunningDuration('2026-08-05T06:00:00Z', '2026-08-05T08:10:00Z'),
    '2h 10m'
  )
})

test('任务完成标题 key 由终态决定，非终态回退 completed', () => {
  assert.equal(getTaskCompletedTitleKey('success'), 'tasks.completed')
  assert.equal(getTaskCompletedTitleKey('failure'), 'tasks.failed')
  assert.equal(getTaskCompletedTitleKey('timeout'), 'tasks.timedOut')
  assert.equal(getTaskCompletedTitleKey('canceled'), 'tasks.canceled')
  assert.equal(getTaskCompletedTitleKey('running'), 'tasks.completed')
  assert.equal(getTaskCompletedTitleKey('queued'), 'tasks.completed')
})

test('任务失败诊断提取 stderr、stdout 和标准产物缺失提示', () => {
  const diagnostics = buildTaskFailureDiagnostics({
    error_message: 'Workflow node missing required standard artifacts: report (run_report@1)',
    outputs: {
      result: {
        success: false,
        details: {
          stdout: 'loading model',
          stderr: 'Missing required output artifact: report'
        }
      },
      file_ids: [],
      output_type: 'json'
    },
    output_data: null
  })

  assert.equal(
    diagnostics.errorMessage,
    'Workflow node missing required standard artifacts: report (run_report@1)'
  )
  assert.equal(diagnostics.stdout, 'loading model')
  assert.equal(diagnostics.stderr, 'Missing required output artifact: report')
  assert.equal(
    diagnostics.standardArtifactMessage,
    'Workflow node missing required standard artifacts: report (run_report@1)'
  )
  assert.equal(diagnostics.hasDetails, true)
})

test('任务失败诊断优先使用后端结构化字段', () => {
  const diagnostics = buildTaskFailureDiagnostics({
    error_message: 'old message',
    failure_diagnostics: {
      error_message: 'server message',
      stdout: 'server stdout',
      stderr: 'server stderr',
      standard_artifact_message: 'server standard artifact hint'
    },
    outputs: {
      result: { stdout: 'raw stdout', stderr: 'raw stderr' },
      file_ids: [],
      output_type: 'json'
    },
    output_data: null
  })

  assert.equal(diagnostics.errorMessage, 'server message')
  assert.equal(diagnostics.stdout, 'server stdout')
  assert.equal(diagnostics.stderr, 'server stderr')
  assert.equal(diagnostics.standardArtifactMessage, 'server standard artifact hint')
})

test('读取排队位置与预计等待时间，缺失时优雅降级', () => {
  const info = readTaskQueueInfo({
    dispatch: { queue: 'gpu_queue', queue_position: 3, estimated_wait_seconds: 240 },
    resource_wait: { reason: 'gpu_unavailable', retry_count: 1 },
  })
  assert.equal(info.queue, 'gpu_queue')
  assert.equal(info.queuePosition, 3)
  assert.equal(info.estimatedWaitSeconds, 240)

  const empty = readTaskQueueInfo({ dispatch: { queue: 'cpu_queue' } })
  assert.equal(empty.queue, 'cpu_queue')
  assert.equal(empty.queuePosition, null)
  assert.equal(empty.estimatedWaitSeconds, null)
})

test('等待时间格式在秒、分钟、小时之间切换', () => {
  assert.equal(formatWaitSeconds(45), '45s')
  assert.equal(formatWaitSeconds(180), '3m')
  assert.equal(formatWaitSeconds(5400), '1h 30m')
  assert.equal(formatWaitSeconds(null), '')
})

test('解析运行中进度文本里的生成数量与最佳评分', () => {
  const detail = parseTaskProgressDetail({
    progress_message: 'Generated 32/100 molecules · best score: 0.72',
    outputs: undefined,
    output_data: null,
  })
  assert.equal(detail.generated, 32)
  assert.equal(detail.total, 100)
  assert.equal(detail.bestScore, 0.72)

  const chinese = parseTaskProgressDetail({
    progress_message: '已生成 12 / 50 个分子',
    outputs: undefined,
    output_data: null,
  })
  assert.equal(chinese.generated, 12)
  assert.equal(chinese.total, 50)
})

test('结构化字段优先于文本解析，且解析不到时不报错', () => {
  const detail = parseTaskProgressDetail({
    progress_message: 'working',
    outputs: { result: null, file_ids: [], output_type: 'json' },
    output_data: { generated_count: 8, total: 20, best_score: 0.91 },
  })
  assert.equal(detail.generated, 8)
  assert.equal(detail.total, 20)
  assert.equal(detail.bestScore, 0.91)

  const empty = parseTaskProgressDetail({ progress_message: '', outputs: undefined, output_data: null })
  assert.equal(empty.generated, null)
  assert.equal(empty.total, null)
  assert.equal(empty.bestScore, null)
})

test('失败诊断按错误码/文本归类并给出可执行建议', () => {
  const oom = buildTaskFailureAdvice({
    status: 'failure',
    error_message: 'CUDA error: out of memory',
    failure_diagnostics: null,
    outputs: undefined,
    output_data: null,
  })
  assert.equal(oom.cause, 'gpu_oom')
  assert.equal(oom.canAdjustParams, true)
  assert.deepEqual(oom.suggestedParams, { num_samples: 20 })

  const pocket = buildTaskFailureAdvice({
    status: 'failure',
    error_message: 'pocket is too small to place any atom',
    failure_diagnostics: null,
    outputs: undefined,
    output_data: null,
  })
  assert.equal(pocket.cause, 'pocket_too_small')
  assert.deepEqual(pocket.suggestedParams, { pocket_radius: 12 })

  const invalidProtein = buildTaskFailureAdvice({
    status: 'failure',
    error_message: 'invalid protein structure: cannot parse PDB',
    failure_diagnostics: null,
    outputs: undefined,
    output_data: null,
  })
  assert.equal(invalidProtein.cause, 'invalid_protein')
  assert.equal(invalidProtein.canAdjustParams, false)
})

test('超时状态优先于文本归类，标准产物缺失单独归类', () => {
  const timeout = buildTaskFailureAdvice({
    status: 'timeout',
    error_message: 'killed after budget',
    failure_diagnostics: null,
    outputs: undefined,
    output_data: null,
  })
  assert.equal(timeout.cause, 'timeout')
  assert.equal(timeout.suggestedParams?.num_samples, 20)

  const missing = buildTaskFailureAdvice({
    status: 'failure',
    error_message: 'Missing required output artifact: report',
    failure_diagnostics: null,
    outputs: undefined,
    output_data: null,
  })
  assert.equal(missing.cause, 'missing_artifact')
})

test('无法识别的失败回退 unknown，仍给出日志建议', () => {
  const advice = buildTaskFailureAdvice({
    status: 'failure',
    error_message: 'something unexpected',
    failure_diagnostics: null,
    outputs: undefined,
    output_data: null,
  })
  assert.equal(advice.cause, 'unknown')
  assert.equal(advice.messageKey, 'tasks.failureAdvice.causes.unknown')
})
