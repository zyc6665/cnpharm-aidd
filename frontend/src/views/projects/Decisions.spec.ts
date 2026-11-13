import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectDecisions from './Decisions.vue'
import type { DecisionRecord, ProjectStage } from '@/types/decisions'

const listProjectDecisionsMock = vi.fn()
const createProjectDecisionMock = vi.fn()
const getProjectStageMock = vi.fn()
const listCandidateSetsMock = vi.fn()
const getTaskListMock = vi.fn()

vi.mock('@/api/decisions', () => ({
  listProjectDecisions: (...args: unknown[]) => listProjectDecisionsMock(...args),
  createProjectDecision: (...args: unknown[]) => createProjectDecisionMock(...args),
  getProjectStage: (...args: unknown[]) => getProjectStageMock(...args)
}))

// 本文件只关心既有列表/表单行为：把候选集与任务列表固定成空，页面就退回纯手填路径，
// 不会因为「本机有没有后端」而抖动。
vi.mock('@/api/compounds', () => ({
  listCandidateSets: (...args: unknown[]) => listCandidateSetsMock(...args),
  listCandidateSetItems: () => Promise.reject(new Error('not used'))
}))

vi.mock('@/api/tasks', () => ({
  getTaskList: (...args: unknown[]) => getTaskListMock(...args)
}))

vi.mock('ant-design-vue', () => ({
  message: { warning: vi.fn(), error: vi.fn(), success: vi.fn() }
}))

/**
 * `t` 用一张小词典而不是恒等函数：断言里要看到真正的中文文案（决策点名称、「未记录」），
 * 否则只能断到 i18n key，等于没验证「渲染出什么」。
 */
const TRANSLATIONS: Record<string, string> = {
  'decisions.points.DP1': '靶点是否值得推进',
  'decisions.points.DP2': '选定结构或口袋作为设计起点',
  'decisions.points.DP3': '哪些候选进入评估',
  'decisions.points.DP4': '哪些候选进入重计算',
  'decisions.points.DP5': '最终推荐进入实验',
  'decisions.snapshot.notRecorded': '未记录',
  'decisions.timeline.selected': '入选 {count}',
  'decisions.timeline.excluded': '淘汰 {count}'
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      const template = TRANSLATIONS[key] ?? key
      if (!params) {
        return template
      }
      return Object.entries(params).reduce(
        (text, [name, value]) => text.replace(`{${name}}`, String(value)),
        template
      )
    }
  })
}))

// 页面只用 `useRoute`（导航一律走 `<router-link>`），因此不 mock `useRouter`。
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} })
}))

const ATableStub = {
  props: ['columns', 'dataSource', 'rowKey', 'pagination', 'size', 'locale'],
  template: `<div class="a-table">
    <div
      v-for="(record, index) in dataSource"
      :key="index"
      class="a-table-row"
    >
      <span v-for="column in columns" :key="column.key" class="a-table-td">
        <slot name="bodyCell" :column="column" :record="record" :index="index" />
      </span>
    </div>
  </div>`
}

const RouterLinkStub = {
  props: ['to'],
  template: '<a class="router-link" :href="String(to)"><slot /></a>'
}

const PassThrough = { template: '<div><slot /></div>' }

/**
 * 分页器桩：把 props 透出成属性、把 `change`/`showSizeChange` 原样转发，
 * 测试里用 `findComponent(APaginationStub).vm.$emit(...)` 复现 antd 的真实 emit 顺序。
 */
const APaginationStub = {
  name: 'APagination',
  props: ['current', 'total', 'pageSize', 'pageSizeOptions', 'showSizeChanger', 'showTotal'],
  emits: ['change', 'showSizeChange', 'update:current', 'update:pageSize'],
  template:
    '<div class="a-pagination-stub" :data-current="current" :data-page-size="pageSize" />'
}

/**
 * 输入桩：需要支持 `v-model:value`，否则抽屉里的表单用例无法写入草稿。
 * 其余断言只读 `data-testid`，因此桩不影响既有用例。
 */
const AInputStub = {
  name: 'AInput',
  props: ['value'],
  emits: ['update:value'],
  template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
}

const ATextareaStub = {
  name: 'ATextarea',
  props: ['value'],
  emits: ['update:value'],
  template: '<textarea :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
}

const stubs = {
  ATable: ATableStub,
  RouterLink: RouterLinkStub,
  AppPageHeader: PassThrough,
  ProjectWorkspaceNav: true,
  AppErrorState: true,
  SkeletonList: true,
  AAlert: PassThrough,
  ASpace: PassThrough,
  AEmpty: {
    props: ['description'],
    template: '<div class="a-empty"><slot name="description" /><slot /></div>'
  },
  ATag: PassThrough,
  ASelect: true,
  APagination: APaginationStub,
  ADrawer: PassThrough,
  AForm: PassThrough,
  AFormItem: PassThrough,
  AInput: AInputStub,
  ATextarea: ATextareaStub,
  AButton: {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs"><slot /></button>'
  }
}

function stage(): ProjectStage {
  return {
    currentStage: 'S6',
    stageName: '决策与归档',
    reachedStages: ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
    nextStage: null,
    gaps: [
      {
        code: 'NO_DECISION',
        message: '已有计算结果，但还没有记录任何研发决策',
        action: '在结果页选择候选并提交决策记录',
        link: '/projects/project-1/decisions'
      }
    ],
    counters: {
      targets: 1,
      structures: 1,
      selected_pockets: 1,
      candidates: 3,
      submitted_tasks: 2,
      finished_tasks: 1,
      decisions: 2
    }
  }
}

/**
 * 一条真实形态的记录：`candidate-1` 当时录了分（0），`candidate-2` 没录分
 * （`snapshot_score = null` 且 `snapshot_attrs.score_source === 'missing'`）。
 */
function decisionRecord(): DecisionRecord {
  return {
    id: 'decision-1',
    project_id: 'project-1',
    decision_point: 'DP3',
    subject_type: 'CANDIDATE_SET',
    subject_id: 'set-1',
    reason: '活性与选择性均达标，淘汰毒性风险较高的两条',
    basis_task_ids: ['task-1'],
    basis_metrics: { pic50: 7.2, admet_pass_rate: 0.86 },
    decided_by: 'lead@example.com',
    decided_by_id: 'user-1',
    // 后端 `_iso()` 产出的是**不带 Z 的 naive UTC**（`app/services/decisions.py`）；
    // fixture 必须照抄这个形态，否则时区 bug 会被一个根本不存在的 `Z` 掩护过去。
    decided_at: '2026-10-05T02:00:00',
    created_at: '2026-10-05T02:00:00',
    selected_ids: ['candidate-1'],
    excluded_ids: ['candidate-2'],
    items: [
      {
        candidate_id: 'candidate-1',
        verdict: 'SELECTED',
        snapshot_score: 0,
        snapshot_rank: 1,
        snapshot_attrs: {}
      },
      {
        candidate_id: 'candidate-2',
        verdict: 'EXCLUDED',
        snapshot_score: null,
        snapshot_rank: null,
        snapshot_attrs: { score_source: 'missing' }
      }
    ]
  }
}

async function mountPage() {
  const wrapper = mount(ProjectDecisions, { global: { stubs } })
  await flushPromises()
  return wrapper
}

describe('决策记录页 P-39', () => {
  beforeEach(() => {
    listProjectDecisionsMock.mockReset()
    createProjectDecisionMock.mockReset()
    getProjectStageMock.mockReset()
    listCandidateSetsMock.mockReset()
    getTaskListMock.mockReset()

    listCandidateSetsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 }
    })
    getTaskListMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 }
    })

    listProjectDecisionsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [decisionRecord()], total: 1, page: 1, page_size: 20, total_pages: 1 }
    })
    getProjectStageMock.mockResolvedValue({ code: 0, message: 'ok', data: stage() })
  })

  it('按决策点分组渲染时间线，展示决策人、理由与入选/淘汰数量', async () => {
    const wrapper = await mountPage()

    expect(getProjectStageMock).toHaveBeenCalledWith('project-1')
    expect(listProjectDecisionsMock).toHaveBeenCalledTimes(1)

    const group = wrapper.get('[data-testid="decisions-group"]')
    expect(group.text()).toContain('哪些候选进入评估')

    const record = wrapper.get('[data-testid="decisions-record"]')
    const recordText = record.text()
    expect(recordText).toContain('lead@example.com')
    expect(recordText).toContain('活性与选择性均达标，淘汰毒性风险较高的两条')
    expect(recordText).toContain('入选 1')
    expect(recordText).toContain('淘汰 1')
  })

  it('展开记录后渲染成员快照：missing 显示「未记录」，0 分显示 0', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="decisions-record-toggle"]').trigger('click')
    await flushPromises()

    const table = wrapper.get('[data-testid="decisions-snapshot-table"]')
    const rows = table.findAll('.a-table-row')
    expect(rows).toHaveLength(2)

    expect(rows[0]!.text()).toContain('candidate-1')
    expect(rows[0]!.text()).toContain('0')
    expect(rows[0]!.text()).not.toContain('未记录')

    expect(rows[1]!.text()).toContain('candidate-2')
    expect(rows[1]!.text()).toContain('未记录')
  })

  it('没有决策记录时给出空态与新建入口，点击后打开新建抽屉', async () => {
    listProjectDecisionsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }
    })

    const wrapper = await mountPage()

    const empty = wrapper.get('[data-testid="decisions-empty"]')
    expect(empty.text()).toContain('decisions.empty.title')

    await wrapper.get('[data-testid="decisions-empty-create"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="decisions-drawer"]').exists()).toBe(true)
  })

  it('决策时间按 UTC 解析后按本机时区展示：naive UTC 02:00 在东八区显示 10:00', async () => {
    // 后端给的是不带 Z 的 naive UTC（`backend/app/services/decisions.py` 的 `_iso()`）。
    // 仓库约定整套测试跑在 `TZ=UTC` 下，那样 naive 串恰好等于本地时间，bug 会被掩盖；
    // 这里临时把进程时区切到东八区，让「按本地时区解释 naive 串」的实现暴露 8 小时偏差。
    const original = process.env.TZ
    process.env.TZ = 'Asia/Shanghai'
    try {
      const wrapper = await mountPage()
      const record = wrapper.get('[data-testid="decisions-record"]')

      expect(record.text()).toContain('2026-10-05 10:00')
      expect(record.text()).not.toContain('2026-10-05 02:00')
    } finally {
      process.env.TZ = original
    }
  })

  it('改 page_size 时回到第 1 页，且只发出一次请求', async () => {
    listProjectDecisionsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [decisionRecord()], total: 120, page: 2, page_size: 20, total_pages: 6 }
    })

    const wrapper = await mountPage()
    const pagination = wrapper.getComponent(APaginationStub)

    // 先翻到第 2 页，再改页大小（否则「没回第 1 页」这个断言看不出区别）。
    pagination.vm.$emit('change', 2, 20)
    await flushPromises()
    expect(pagination.props('current')).toBe(2)

    const callsBefore = listProjectDecisionsMock.mock.calls.length

    // antd 的 `changePageSize` 先 emit `showSizeChange`，再 emit `change`；
    // 两个事件都发，模拟真实交互（`node_modules/ant-design-vue/es/vc-pagination/Pagination.js`）。
    pagination.vm.$emit('showSizeChange', 2, 50)
    pagination.vm.$emit('change', 2, 50)
    await flushPromises()

    expect(listProjectDecisionsMock.mock.calls.length - callsBefore).toBe(1)
    expect(listProjectDecisionsMock).toHaveBeenLastCalledWith('project-1', {
      page: 1,
      page_size: 50
    })
    expect(pagination.props('current')).toBe(1)
    expect(pagination.props('pageSize')).toBe(50)
  })

  it('加载失败时渲染错态与重试按钮，点重试会重新请求', async () => {
    listProjectDecisionsMock.mockRejectedValueOnce(new Error('Network Error'))

    const wrapper = await mountPage()

    // `get` 在节点缺失时会直接抛错，本身已断言了错态存在。
    expect(wrapper.get('[data-testid="decisions-error"]').text()).not.toBe('')
    expect(wrapper.find('[data-testid="decisions-timeline"]').exists()).toBe(false)

    // 第一页（含失败那次）已经过的调用次数，重试后应再 +1。
    const callsBefore = listProjectDecisionsMock.mock.calls.length

    await wrapper.get('[data-testid="decisions-error-retry"]').trigger('click')
    await flushPromises()

    expect(listProjectDecisionsMock.mock.calls.length).toBeGreaterThan(callsBefore)
    expect(wrapper.find('[data-testid="decisions-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="decisions-timeline"]').exists()).toBe(true)
  })

  it('依据指标不是合法 JSON 时，抽屉里显示表单错误且不提交', async () => {
    // 走空态入口打开抽屉：`AppPageHeader` 的 `#actions` 插槽在桩里不渲染，空态按钮更直接。
    listProjectDecisionsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }
    })

    const wrapper = await mountPage()

    await wrapper.get('[data-testid="decisions-empty-create"]').trigger('click')
    await flushPromises()

    const setValue = async (testId: string, value: string): Promise<void> => {
      const input = wrapper.get(`[data-testid="${testId}"]`)
      await input.setValue(value)
    }

    await setValue('decisions-drawer-subject-id', 'set-1')
    await setValue('decisions-drawer-reason', '活性与选择性均达标')
    await setValue('decisions-drawer-selected', 'candidate-1')
    // 占位符早期写的是「形如 pic50: 7.2」，用户照抄的正是这种非 JSON 输入。
    await setValue('decisions-drawer-basis-metrics', 'pic50: 7.2')

    await wrapper.get('[data-testid="decisions-drawer-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="decisions-drawer-error"]').text()).toBe(
      'decisions.drawer.basisMetricsInvalid'
    )
    expect(createProjectDecisionMock).not.toHaveBeenCalled()

    // 改成合法 JSON 后同一按钮能正常提交，说明拦的只是格式而不是整条路径。
    await setValue('decisions-drawer-basis-metrics', '{"pic50": 7.2}')
    await wrapper.get('[data-testid="decisions-drawer-submit"]').trigger('click')
    await flushPromises()

    expect(createProjectDecisionMock).toHaveBeenCalledTimes(1)
    expect(createProjectDecisionMock).toHaveBeenCalledWith(
      'project-1',
      expect.objectContaining({ basis_metrics: { pic50: 7.2 } })
    )
  })
})
