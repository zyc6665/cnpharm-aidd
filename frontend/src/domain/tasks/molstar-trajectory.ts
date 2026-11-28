/**
 * Mol* 多帧轨迹播放的纯函数域层（无副作用、可在 node 环境直接测试）。
 *
 * 与 `MoleculeViewer.vue` 的底部轨迹播放条配套：帧索引裁剪、步进、播放间隔与帧标签
 * 都在这里定义，组件只负责把结果落到 Mol* 状态树（`ModelFromTrajectory.modelIndex`）。
 */

/** 可选播放倍速（相对基准帧率）。 */
export const TRAJECTORY_PLAYBACK_SPEEDS = [0.5, 1, 2, 4] as const

export type TrajectoryPlaybackSpeed = (typeof TRAJECTORY_PLAYBACK_SPEEDS)[number]

/** 基准播放帧率（每秒帧数），播放间隔 = 1000 / (baseFps * speed)。 */
export const BASE_TRAJECTORY_FPS = 8

/** 把帧索引裁剪到 `[0, frameCount - 1]`；非法输入按 0 处理。 */
export function clampFrameIndex(index: number, frameCount: number): number {
  const count = Math.max(1, Math.floor(Number(frameCount) || 1))
  const raw = Number(index)
  const value = Number.isFinite(raw) ? Math.floor(raw) : 0
  if (value < 0) return 0
  if (value > count - 1) return count - 1
  return value
}

/**
 * 从当前帧步进 `delta`（可为负）。
 *
 * - `loop = true`：环形回绕，永远返回 `[0, frameCount - 1]` 内的索引；
 * - `loop = false`：越过首尾时返回 `null`，交由调用方停止播放（单次播放到末尾）。
 * - 单帧轨迹恒返回 0。
 */
export function stepFrameIndex(
  current: number,
  delta: number,
  frameCount: number,
  loop: boolean
): number | null {
  const count = Math.max(1, Math.floor(Number(frameCount) || 1))
  if (count <= 1) return 0
  const curRaw = Number(current)
  const delRaw = Number(delta)
  const cur = Number.isFinite(curRaw) ? Math.floor(curRaw) : 0
  const del = Number.isFinite(delRaw) ? Math.floor(delRaw) : 0
  const next = cur + del
  if (loop) {
    return ((next % count) + count) % count
  }
  if (next < 0 || next > count - 1) return null
  return next
}

/** 计算播放定时器间隔（毫秒），对非法/非正输入退化为 1x 基准帧率。 */
export function computeFrameIntervalMs(
  speed: TrajectoryPlaybackSpeed,
  baseFps: number = BASE_TRAJECTORY_FPS
): number {
  const fps = Number(baseFps) > 0 && Number.isFinite(Number(baseFps)) ? Number(baseFps) : BASE_TRAJECTORY_FPS
  const normalizedSpeed = Number(speed) > 0 && Number.isFinite(Number(speed)) ? Number(speed) : 1
  return Math.round(1000 / (fps * normalizedSpeed))
}

/** 去掉浮点尾巴的 ps 时间展示（最多两位小数）。 */
function formatPsTime(time: number): string {
  return String(Math.round(time * 100) / 100)
}

/**
 * 播放下标帧标签，如 `3 / 100`；若提供 `frameTimesPs` 则追加物理时间，如 `3 / 100 · 12.5 ps`。
 * 展示用 1 基（用户看到的「第几帧」），内部 `index` 仍是 0 基。
 */
export function formatTrajectoryFrameLabel(
  index: number,
  frameCount: number,
  frameTimesPs?: number[] | null
): string {
  const count = Math.max(1, Math.floor(Number(frameCount) || 1))
  const clamped = clampFrameIndex(index, count)
  const base = `${clamped + 1} / ${count}`
  const time = Array.isArray(frameTimesPs) ? frameTimesPs[clamped] : undefined
  if (typeof time === 'number' && Number.isFinite(time)) {
    return `${base} · ${formatPsTime(time)} ps`
  }
  return base
}
