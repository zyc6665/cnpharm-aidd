/**
 * 测试时区固定为 UTC。
 *
 * CI（ubuntu-latest）默认就是 UTC，而本地 Windows 开发机常是 UTC+8：
 * 同一批「后端返回不带时区的 UTC 字符串」的日期断言，在两边会得到不同小时数。
 * 这里在测试启动时统一到 CI 口径，避免「本地红、CI 绿」的假失败；
 * 需要其他时区的用例（如决策记录）仍可在用例内自行覆盖 process.env.TZ。
 */
process.env.TZ = 'UTC'
