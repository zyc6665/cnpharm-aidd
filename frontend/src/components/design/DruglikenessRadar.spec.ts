import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DruglikenessRadar from './DruglikenessRadar.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params?.count !== undefined ? `${key}:${params.count}` : key,
  }),
}))

interface LabelCall {
  text: string
  align: string
  baseline: string
}

function fakeContext(): { ctx: Record<string, unknown>; labels: LabelCall[] } {
  const labels: LabelCall[] = []
  const ctx: Record<string, unknown> = {
    setLineDash: vi.fn(),
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    arc: vi.fn(),
    fillText: vi.fn(function (this: Record<string, unknown>, text: string) {
      labels.push({
        text,
        align: String(this.textAlign ?? ''),
        baseline: String(this.textBaseline ?? ''),
      })
    }),
    strokeStyle: '',
    lineWidth: 0,
    fillStyle: '',
    font: '',
    textAlign: '',
    textBaseline: '',
  }
  return { ctx, labels }
}

describe('DruglikenessRadar', () => {
  beforeEach(() => {
    // jsdom 没有 canvas 2d 实现；默认返回 null，需要绘制断言的用例再覆盖。
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  })

  it('渲染 canvas 并暴露越界数量', () => {
    const wrapper = mount(DruglikenessRadar, {
      props: {
        properties: { mw: 780, logp: 2, hbd: 1, hba: 3, tpsa: 80, qed: 0.4 },
        size: 140,
      },
    })

    expect(wrapper.find('canvas').exists()).toBe(true)
    expect(wrapper.get('[data-testid="druglikeness-radar"]').attributes('data-violations')).toBe('1')
    expect(wrapper.find('.druglikeness-radar__empty').exists()).toBe(false)
  })

  it('没有性质数据时不渲染 canvas，只显示空态', () => {
    const wrapper = mount(DruglikenessRadar, {
      props: {
        properties: { mw: null, logp: null, hbd: null, hba: null, tpsa: null, qed: null },
      },
    })

    expect(wrapper.find('canvas').exists()).toBe(false)
    expect(wrapper.find('.druglikeness-radar__empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('design.results.druglikeness.noData')
    expect(wrapper.get('[data-testid="druglikeness-radar"]').attributes('data-violations')).toBe('0')
  })

  it('大尺寸使用缩写轴标签，并按象限对齐避免重叠', () => {
    const { ctx, labels } = fakeContext()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      ctx as unknown as CanvasRenderingContext2D
    )

    mount(DruglikenessRadar, {
      props: {
        properties: { mw: 400, logp: 2, hbd: 1, hba: 3, tpsa: 80, qed: 0.7 },
        size: 240,
      },
    })

    expect(labels.map((label) => label.text)).toEqual([
      'design.results.druglikeness.axis.mw',
      'design.results.druglikeness.axis.logp',
      'design.results.druglikeness.axis.hbd',
      'design.results.druglikeness.axis.hba',
      'design.results.druglikeness.axis.tpsa',
    ])
    // 顶部居中、右/左侧文字朝外对齐，不能全部 center。
    expect(new Set(labels.map((label) => label.align))).toEqual(new Set(['center', 'left', 'right']))
    expect(labels[0]?.baseline).toBe('bottom')
  })
})
