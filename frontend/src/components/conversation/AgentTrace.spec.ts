import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentTrace from './AgentTrace.vue'
import type { AgentEvent } from '@/types/conversations'

const baseEvent = (
  event: Partial<AgentEvent> & { sequence: number; event_type: string }
): AgentEvent => ({
  id: `event-${event.sequence}`,
  payload: {},
  ...event
})

function renderTrace(events: AgentEvent[], showRetry = false) {
  return mount(AgentTrace, {
    props: { events, showRetry },
    global: {
      stubs: {
        AButton: {
          template: '<button data-testid="retry-run" @click="$emit(\'click\')"><slot /></button>'
        }
      }
    }
  })
}

describe('AgentTrace', () => {
  it('展示任务执行事件的状态、短任务号和进度', async () => {
    const wrapper = renderTrace([
      baseEvent({
        sequence: 1,
        event_type: 'execution_started',
        payload: {
          task_id: 'task-1234567890abcdef',
          status: 'running',
          progress: 5,
          message: '任务开始执行'
        }
      }),
      baseEvent({
        sequence: 2,
        event_type: 'execution_progress',
        payload: {
          task_id: 'task-1234567890abcdef',
          status: 'running',
          progress: 55,
          message: '远端运行中：sampling'
        }
      }),
      baseEvent({
        sequence: 3,
        event_type: 'execution_completed',
        payload: {
          task_id: 'task-1234567890abcdef',
          status: 'success',
          progress: 100,
          message: '任务执行成功'
        }
      })
    ])

    await wrapper.get('.trace-toggle').trigger('click')

    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.text()).toContain('task-123')
    expect(wrapper.text()).toContain('55%')
    expect(wrapper.find('[data-testid="agent-event-progress"]').attributes('aria-valuenow')).toBe(
      '5'
    )
  })

  it('失败事件展示错误状态并保留重试入口', async () => {
    const wrapper = renderTrace([
      baseEvent({
        sequence: 1,
        event_type: 'execution_failed',
        payload: {
          task_id: 'task-failed-001',
          status: 'failure',
          progress: 70,
          message: '任务失败: boom',
          error: 'boom'
        }
      })
    ])

    await wrapper.get('.trace-toggle').trigger('click')

    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('任务失败: boom')
    expect(wrapper.text()).toContain('70%')
    expect(wrapper.find('[data-testid="retry-run"]').exists()).toBe(true)
  })
})
