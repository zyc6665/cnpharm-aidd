import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectDecisions from './Decisions.vue'
import type { Candidate, CandidateSetItem } from '@/types/compounds'

/**
 * 抽屉里的「对象 / 成员」选择器。
 *
 * 记录一次决策原本要求手敲候选集 UUID 和成员 ID——这是本页最主要的入口，
 * 却只有在知道 UUID 的前提下才用得起来。这里锁住三条契约：
 *   1. 有候选集时对象字段变成下拉，没有时退回输入框（功能不因空列表消失）；
 *   2. 选定候选集后按需拉成员，成员以 `candidate_id` 为值、名称+id+分数为标签；
 *   3. 选择器最终只写回 `selectedIdsText` / `excludedIdsText`，
 *      提交仍然走 `buildDecisionCreatePayload`，不绕过既有校验。
 */

const TRANSLATIONS: Record<string, string> = {
  'decisions.drawer.memberListHint': '候选集共 {count} 个成员，点选后自动记入快照',
  'decisions.drawer.memberListTooLarge': '候选集成员过多（共 {count} 个），请直接填写成员 ID',
  'tasks.statusSuccess': '已完成'
}

const listProjectDecisionsMock = vi.fn()
const createProjectDecisionMock = vi.fn()
const getProjectStageMock = vi.fn()
const listCandidateSetsMock = vi.fn()
const listCandidateSetItemsMock = vi.fn()
const getTaskListMock = vi.fn()

vi.mock('@/api/decisions', () => ({
  listProjectDecisions: (...args: unknown[]) => listProjectDecisionsMock(...args),
  createProjectDecision: (...args: unknown[]) => createProjectDecisionMock(...args),
  getProjectStage: (...args: unknown[]) => getProjectStageMock(...args)
}))

vi.mock('@/api/tasks', () => ({
  getTaskList: (...args: unknown[]) => getTaskListMock(...args)
}))

vi.mock('@/api/compounds', () => ({
  listCandidateSets: (...args: unknown[]) => listCandidateSetsMock(...args),
  listCandidateSetItems: (...args: unknown[]) => listCandidateSetItemsMock(...args)
}))

vi.mock('ant-design-vue', () => ({
  message: { warning: vi.fn(), error: vi.fn(), success: vi.fn() }
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      // 只给带插值的几条文案配词典，其余直接回 key：断言要看到真实的中文提示。
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

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} })
}))

const PassThrough = { template: '<div><slot /></div>' }
const RouterLinkStub = {
  props: ['to'],
  template: '<a class="router-link" :href="String(to)"><slot /></a>'
}

const ATableStub = {
  props: ['columns', 'dataSource', 'rowKey', 'pagination', 'size', 'locale'],
  template: '<div class="a-table"><slot name="bodyCell" /></div>'
}

const AInputStub = {
  name: 'AInput',
  inheritAttrs: false,
  props: ['value'],
  emits: ['update:value'],
  template:
    '<input v-bind="$attrs" :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
}

const ATextareaStub = {
  name: 'ATextarea',
  props: ['value'],
  emits: ['update:value'],
  template: '<textarea :value="value" @input="$emit(\'update:value\', $event.target.value)" />'
}

/** 下拉桩：把 props 摆到根节点上，测试用 `data-testid` 定位后直接 emit。 */
const ASelectStub = {
  name: 'ASelect',
  props: ['value', 'options', 'mode', 'loading', 'placeholder', 'showSearch'],
  emits: ['update:value', 'change'],
  template: '<div v-bind="$attrs" :data-mode="mode || \'single\'"></div>'
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
  AEmpty: { template: '<div class="a-empty"><slot name="description" /><slot /></div>' },
  ATag: PassThrough,
  ASelect: ASelectStub,
  APagination: true,
  ADrawer: PassThrough,
  AForm: PassThrough,
  AFormItem: PassThrough,
  AInput: AInputStub,
  ATextarea: ATextareaStub,
  AButton: {
    inheritAttrs: false,
    template: '<button type="button" v-bind="$attrs"><slot /></button>'
  },
  ADescriptions: PassThrough,
  ADescriptionsItem: PassThrough
}

/**
 * 候选物夹具：`Candidate` 还有十几个后端字段，这里只关心选择器要用的名称/编号，
 * 其余字段与本页无关，因此显式收窄成页面实际读取的形状。
 */
function candidateOf(id: string, name: string, code: string | null): Candidate {
  return { id, name, code } as Candidate
}

function candidateSetItem(overrides: Partial<CandidateSetItem> = {}): CandidateSetItem {
  return {
    id: 'item-1',
    set_id: 'set-1',
    candidate_id: 'candidate-1',
    ordinal: 1,
    snapshot_score: 7.42,
    candidate: candidateOf('candidate-1', 'Pocket2Mol-001', 'PM-001'),
    ...overrides
  } as CandidateSetItem
}

function emptyPage(): {
  code: number
  message: string
  data: { items: never[]; total: number; page: number; page_size: number; total_pages: number }
} {
  return {
    code: 0,
    message: 'ok',
    data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 1 }
  }
}

async function mountPage() {
  const wrapper = mount(ProjectDecisions, { global: { stubs } })
  await flushPromises()
  // 有记录时入口在页头，空态时在空状态里——两条路径都指向同一个抽屉。
  const opener = wrapper.find('[data-testid="decisions-create"]')
  const entry = opener.exists() ? opener : wrapper.get('[data-testid="decisions-empty-create"]')
  await entry.trigger('click')
  await flushPromises()
  return wrapper
}

/** 按 testid 找到抽屉里的下拉桩：`stubs` 里的 ASelect 是固定组件，按组件实例捞更稳。 */
function selectBy(wrapper: ReturnType<typeof mount>, testid: string) {
  const match = wrapper
    .findAllComponents(ASelectStub)
    .find(component => component.attributes('data-testid') === testid)
  if (!match) {
    throw new Error(`抽屉里没有 testid 为 ${testid} 的下拉`)
  }
  return match
}

/** 抽屉里的下拉：模拟 antd 的 `update:value` + `change` 双 emit。 */
async function pick(wrapper: Awaited<ReturnType<typeof mountPage>>, testid: string, value: unknown) {
  const select = selectBy(wrapper, testid)
  select.vm.$emit('update:value', value)
  select.vm.$emit('change', value)
  await flushPromises()
}

async function typeInto(
  wrapper: Awaited<ReturnType<typeof mountPage>>,
  testid: string,
  value: string
) {
  await wrapper.get(`[data-testid="${testid}"]`).setValue(value)
  await flushPromises()
}

describe('决策记录页 · 新建抽屉的选择器', () => {
  beforeEach(() => {
    listProjectDecisionsMock.mockReset()
    createProjectDecisionMock.mockReset()
    getProjectStageMock.mockReset()
    listCandidateSetsMock.mockReset()
    listCandidateSetItemsMock.mockReset()
    getTaskListMock.mockReset()

    listProjectDecisionsMock.mockResolvedValue(emptyPage())
    getProjectStageMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { currentStage: 'S1', stageName: '靶点确立', reachedStages: [], nextStage: 'S2', gaps: [] }
    })
    listCandidateSetsMock.mockResolvedValue(emptyPage())
    listCandidateSetItemsMock.mockResolvedValue(emptyPage())
    getTaskListMock.mockResolvedValue(emptyPage())
  })

  it('没有候选集时保留手填输入框', async () => {
    const wrapper = await mountPage()

    expect(listCandidateSetsMock).toHaveBeenCalledTimes(1)
    const subjectField = wrapper.get('[data-testid="decisions-drawer-subject-id"]')
    expect(subjectField.element.tagName).toBe('INPUT')
  })

  it('有候选集时对象字段变成下拉，并列出候选集名称', async () => {
    listCandidateSetsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [
          { id: 'set-1', name: 'Pocket2Mol 生成集' },
          { id: 'set-2', name: 'DiffSBDD 结果集' }
        ],
        total: 2,
        page: 1,
        page_size: 100,
        total_pages: 1
      }
    })

    const wrapper = await mountPage()

    const select = selectBy(wrapper, 'decisions-drawer-subject-id')
    expect(select.props('options')).toEqual([
      { value: 'set-1', label: 'Pocket2Mol 生成集' },
      { value: 'set-2', label: 'DiffSBDD 结果集' }
    ])
    // 未选对象前不请求成员，避免每次打开抽屉都打一发。
    expect(listCandidateSetItemsMock).not.toHaveBeenCalled()
  })

  it('选定候选集后拉一页成员，标签带名称、短 id 与分数', async () => {
    listCandidateSetsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [{ id: 'set-1', name: 'Pocket2Mol 生成集' }],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1
      }
    })
    listCandidateSetItemsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [
          candidateSetItem(),
          candidateSetItem({
            id: 'item-2',
            candidate_id: 'candidate-2',
            ordinal: 2,
            snapshot_score: null,
            candidate: candidateOf('candidate-2', 'Pocket2Mol-002', 'PM-002')
          }),
          // 真实数据里 candidate_id 是 UUID：整串写进标签会把名称挤没，只留前 8 位。
          candidateSetItem({
            id: 'item-3',
            candidate_id: '6c73ab3b-1e77-40b3-86c1-8b59335d912a',
            ordinal: 3,
            snapshot_score: 0,
            candidate: candidateOf('6c73ab3b-1e77-40b3-86c1-8b59335d912a', 'Pocket2Mol-003', null)
          })
        ],
        total: 3,
        page: 1,
        page_size: 500,
        total_pages: 1
      }
    })

    const wrapper = await mountPage()
    await pick(wrapper, 'decisions-drawer-subject-id', 'set-1')

    expect(listCandidateSetItemsMock).toHaveBeenCalledWith('set-1', { page: 1, page_size: 500 })

    const selected = selectBy(wrapper, 'decisions-drawer-selected')
    expect(selected.props('mode')).toBe('multiple')
    expect(selected.props('options')).toEqual([
      { value: 'candidate-1', label: 'Pocket2Mol-001 · candidate-1 · 7.42' },
      { value: 'candidate-2', label: 'Pocket2Mol-002 · candidate-2' },
      { value: '6c73ab3b-1e77-40b3-86c1-8b59335d912a', label: 'Pocket2Mol-003 · 6c73ab3b · 0' }
    ])
    expect(wrapper.get('[data-testid="decisions-drawer-member-hint"]').text()).toContain('3')
  })

  it('点选成员后写回逗号分隔文本，提交时照常走既有校验', async () => {
    listCandidateSetsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [{ id: 'set-1', name: 'Pocket2Mol 生成集' }],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1
      }
    })
    listCandidateSetItemsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [
          candidateSetItem(),
          candidateSetItem({
            id: 'item-2',
            candidate_id: 'candidate-2',
            ordinal: 2,
            candidate: candidateOf('candidate-2', 'Pocket2Mol-002', 'PM-002')
          })
        ],
        total: 2,
        page: 1,
        page_size: 500,
        total_pages: 1
      }
    })
    createProjectDecisionMock.mockResolvedValue({ code: 0, message: 'ok', data: null })

    const wrapper = await mountPage()
    await pick(wrapper, 'decisions-drawer-subject-id', 'set-1')
    await typeInto(wrapper, 'decisions-drawer-reason', '活性达标，保留一条进入评估')
    await pick(wrapper, 'decisions-drawer-selected', ['candidate-1'])
    await pick(wrapper, 'decisions-drawer-excluded', ['candidate-2'])

    // 淘汰成员的下拉里剔掉已入选的项，避免同一条既入选又淘汰（后端会 422）。
    expect(
      selectBy(wrapper, 'decisions-drawer-excluded').props('options')
    ).toEqual([{ value: 'candidate-2', label: 'Pocket2Mol-002 · candidate-2 · 7.42' }])

    await wrapper.get('[data-testid="decisions-drawer-submit"]').trigger('click')
    await flushPromises()

    expect(createProjectDecisionMock).toHaveBeenCalledWith('project-1', {
      decision_point: 'DP3',
      subject_type: 'CANDIDATE_SET',
      subject_id: 'set-1',
      selected_ids: ['candidate-1'],
      excluded_ids: ['candidate-2'],
      basis_task_ids: [],
      basis_metrics: {},
      reason: '活性达标，保留一条进入评估',
      snapshot: [
        { candidate_id: 'candidate-1', score: null },
        { candidate_id: 'candidate-2', score: null }
      ]
    })
  })

  it('成员超过一页时退回手填并说明原因，不静默丢掉成员', async () => {
    listCandidateSetsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [{ id: 'set-1', name: '超大候选集' }],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1
      }
    })
    listCandidateSetItemsMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: { items: [candidateSetItem()], total: 600, page: 1, page_size: 500, total_pages: 2 }
    })

    const wrapper = await mountPage()
    await pick(wrapper, 'decisions-drawer-subject-id', 'set-1')

    const selected = wrapper.get('[data-testid="decisions-drawer-selected"]')
    expect(selected.element.tagName).toBe('INPUT')
    expect(wrapper.get('[data-testid="decisions-drawer-member-limit"]').text()).toContain('600')
  })

  it('依据任务：有任务时变成下拉，标签带任务名与状态', async () => {
    getTaskListMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [
          { id: 'task-1', name: '口袋预测 · EGFR', status: 'success', tool_id: 'tool-1' },
          { id: 'task-2', tool_name: 'Pocket2Mol', status: 'success', tool_id: 'tool-2' }
        ],
        total: 2,
        page: 1,
        page_size: 100,
        total_pages: 1
      }
    })

    const wrapper = await mountPage()

    // 抽屉一开就按项目拉一页任务：让人从列表里点，而不是去任务中心抄 UUID。
    expect(getTaskListMock).toHaveBeenCalledWith({
      project_id: 'project-1',
      page: 1,
      page_size: 100
    })

    const select = selectBy(wrapper, 'decisions-drawer-basis-tasks')
    expect(select.props('mode')).toBe('multiple')
    expect(select.props('options')).toEqual([
      { value: 'task-1', label: '口袋预测 · EGFR · 已完成' },
      // 没名字的任务退回工具名，同样是「看得懂」的标签。
      { value: 'task-2', label: 'Pocket2Mol · 已完成' }
    ])
  })

  it('选中依据任务后随提交写入 basis_task_ids', async () => {
    getTaskListMock.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: {
        items: [{ id: 'task-1', name: '口袋预测 · EGFR', status: 'success', tool_id: 'tool-1' }],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1
      }
    })
    createProjectDecisionMock.mockResolvedValue({ code: 0, message: 'ok', data: null })

    const wrapper = await mountPage()
    await typeInto(wrapper, 'decisions-drawer-subject-id', 'set-1')
    await typeInto(wrapper, 'decisions-drawer-reason', '口袋预测结果支撑这一批候选')
    await typeInto(wrapper, 'decisions-drawer-selected', 'candidate-1')
    await pick(wrapper, 'decisions-drawer-basis-tasks', ['task-1'])

    await wrapper.get('[data-testid="decisions-drawer-submit"]').trigger('click')
    await flushPromises()

    expect(createProjectDecisionMock).toHaveBeenCalledWith('project-1', {
      decision_point: 'DP3',
      subject_type: 'CANDIDATE_SET',
      subject_id: 'set-1',
      selected_ids: ['candidate-1'],
      excluded_ids: [],
      basis_task_ids: ['task-1'],
      basis_metrics: {},
      reason: '口袋预测结果支撑这一批候选',
      snapshot: [{ candidate_id: 'candidate-1', score: null }]
    })
  })
})
