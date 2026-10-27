/**
 * 密码强度到颜色的映射。
 *
 * 抽出来是因为注册页与找回密码页各抄了一份一模一样的数组（`['', '#ff4d4f',
 * '#faad14', '#52c41a', '#1890ff']`），改一处忘一处就会出现「同一个密码在两个页面
 * 显示成两种颜色」。
 *
 * 这五个值取的是 ant-design 的语义色板而不是主题变量：强度条是**状态信号**，
 * 和 antd 的 error/warning/success/processing 标签必须同色，否则同一个密码在
 * 输入框下方是橙黄、在旁边的标签里是另一种黄。
 */
export const PASSWORD_STRENGTH_COLORS: readonly string[] = [
  '',
  '#ff4d4f', // 1 弱 → antd red-5
  '#faad14', // 2 中 → antd gold-6
  '#52c41a', // 3 强 → antd green-6
  '#1890ff' // 4 很强 → antd blue-6
]

/** 越界或未输入时返回空串，调用方据此隐藏强度条。 */
export function passwordStrengthColor(level: number): string {
  if (!Number.isFinite(level) || level < 1) return ''
  return PASSWORD_STRENGTH_COLORS[Math.min(Math.trunc(level), PASSWORD_STRENGTH_COLORS.length - 1)] ?? ''
}
