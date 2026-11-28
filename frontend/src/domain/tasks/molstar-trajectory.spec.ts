import { describe, expect, it } from 'vitest'
import {
  BASE_TRAJECTORY_FPS,
  TRAJECTORY_PLAYBACK_SPEEDS,
  clampFrameIndex,
  computeFrameIntervalMs,
  formatTrajectoryFrameLabel,
  stepFrameIndex,
} from './molstar-trajectory'

describe('TRAJECTORY_PLAYBACK_SPEEDS / BASE_TRAJECTORY_FPS', () => {
  it('exposes the fixed playback speed ladder and base fps', () => {
    expect(TRAJECTORY_PLAYBACK_SPEEDS).toEqual([0.5, 1, 2, 4])
    expect(BASE_TRAJECTORY_FPS).toBe(8)
  })
})

describe('clampFrameIndex', () => {
  it('clamps within [0, frameCount - 1]', () => {
    expect(clampFrameIndex(-5, 10)).toBe(0)
    expect(clampFrameIndex(0, 10)).toBe(0)
    expect(clampFrameIndex(4, 10)).toBe(4)
    expect(clampFrameIndex(99, 10)).toBe(9)
  })

  it('degrades gracefully for invalid frame counts and indices', () => {
    expect(clampFrameIndex(3, 0)).toBe(0)
    expect(clampFrameIndex(Number.NaN, 10)).toBe(0)
    expect(clampFrameIndex(2, -1)).toBe(0)
    expect(clampFrameIndex(2.9, 10)).toBe(2)
  })
})

describe('stepFrameIndex', () => {
  it('moves forward/backward inside range without looping', () => {
    expect(stepFrameIndex(3, 1, 10, false)).toBe(4)
    expect(stepFrameIndex(3, -1, 10, false)).toBe(2)
  })

  it('returns null at the ends when loop is disabled', () => {
    expect(stepFrameIndex(9, 1, 10, false)).toBeNull()
    expect(stepFrameIndex(0, -1, 10, false)).toBeNull()
  })

  it('wraps around when loop is enabled', () => {
    expect(stepFrameIndex(9, 1, 10, true)).toBe(0)
    expect(stepFrameIndex(0, -1, 10, true)).toBe(9)
  })

  it('always returns 0 for a single-frame trajectory', () => {
    expect(stepFrameIndex(0, 1, 1, false)).toBe(0)
    expect(stepFrameIndex(0, 1, 1, true)).toBe(0)
  })
})

describe('computeFrameIntervalMs', () => {
  it('scales timer interval inversely with speed against the base fps', () => {
    expect(computeFrameIntervalMs(1)).toBe(Math.round(1000 / BASE_TRAJECTORY_FPS))
    expect(computeFrameIntervalMs(2)).toBe(Math.round(1000 / (BASE_TRAJECTORY_FPS * 2)))
    expect(computeFrameIntervalMs(0.5)).toBe(Math.round(1000 / (BASE_TRAJECTORY_FPS * 0.5)))
    expect(computeFrameIntervalMs(4)).toBe(Math.round(1000 / (BASE_TRAJECTORY_FPS * 4)))
  })

  it('falls back to 1x on invalid speed', () => {
    expect(computeFrameIntervalMs(0 as unknown as 1)).toBe(Math.round(1000 / BASE_TRAJECTORY_FPS))
    expect(computeFrameIntervalMs(-2 as unknown as 1)).toBe(Math.round(1000 / BASE_TRAJECTORY_FPS))
  })
})

describe('formatTrajectoryFrameLabel', () => {
  it('renders a 1-based counter without times', () => {
    expect(formatTrajectoryFrameLabel(0, 100)).toBe('1 / 100')
    expect(formatTrajectoryFrameLabel(4, 100)).toBe('5 / 100')
  })

  it('appends physical time when frameTimesPs is provided', () => {
    expect(formatTrajectoryFrameLabel(0, 10, [0, 2, 4, 6])).toBe('1 / 10 · 0 ps')
    expect(formatTrajectoryFrameLabel(1, 10, [0, 12.5, 25])).toBe('2 / 10 · 12.5 ps')
  })

  it('handles out-of-range indices and missing time entries', () => {
    expect(formatTrajectoryFrameLabel(999, 10)).toBe('10 / 10')
    expect(formatTrajectoryFrameLabel(2, 10, [0])).toBe('3 / 10')
  })
})
