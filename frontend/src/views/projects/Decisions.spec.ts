import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectDecisions from './Decisions.vue'
import type { DecisionRecord, ProjectStage } from '@/types/decisions'

const listProjectDecisionsMock = vi.fn()
const createProjectDecisionMock = vi.fn()
const getProjectStageMock = vi.fn()

vi.mock('@/api/decisions', () => ({
  listProjectDecisions: (...args: unknown[]) => listProjectDecisionsMock(...args),
  createProjectDecision: (...args: unknown[]) => createProjectDecisionMock(...args),
  getProjectStage: (...args: unknown[]) => getProjectStageMock(...args)
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

const routerPushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} }),
  useRouter: () => ({ push: routerPushMock })
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
  APagination: true,
  ADrawer: PassThrough,
  AForm: PassThrough,
  AFormItem: PassThrough,
  AInput: true,
  ATextarea: true,
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
    decided_at: '2026-10-05T02:00:00Z',
    created_at: '2026-10-05T02:00:00Z',
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
    routerPushMock.mockReset()

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
})
