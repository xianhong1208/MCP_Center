/**
 * MCP 設定 JSON 解析(純函式,無 React 相依 — 可獨立測試)
 *
 * 支援使用者從 MCP 市集/官方文件複製的兩種常見形態:
 *   1. Claude Desktop / mcpmarket 格式:
 *      { "mcpServers": { "<name>": { command, args, env } } }
 *   2. 單一 server 物件:{ command, args, env }
 */

/** 後端 argv_policy._ALLOWED_BYO_COMMANDS 的前端對照(需保持一致) */
export const BYO_COMMANDS = ['npx', 'node', 'uvx', 'python', 'python3']

/**
 * @param {string} text 貼上的 JSON 文字
 * @returns {{name: string, command: string, args: string[], env: object, extraCount: number}|null}
 *          解析失敗回 null
 */
export function parseMcpConfigJson(text) {
  let obj
  try {
    obj = JSON.parse(text)
  } catch {
    return null
  }
  if (!obj || typeof obj !== 'object') return null

  let name = ''
  let server = null
  let extraCount = 0

  if (obj.mcpServers && typeof obj.mcpServers === 'object') {
    const keys = Object.keys(obj.mcpServers)
    if (keys.length === 0) return null
    name = keys[0] // 多筆時取第一筆,UI 會提示其餘未帶入
    server = obj.mcpServers[name]
    extraCount = keys.length - 1
  } else if (obj.command) {
    server = obj
  } else {
    return null
  }

  if (!server || typeof server !== 'object' || !server.command) return null

  return {
    name,
    command: String(server.command),
    args: Array.isArray(server.args) ? server.args.map(String) : [],
    env: server.env && typeof server.env === 'object' ? server.env : {},
    extraCount,
  }
}

/**
 * 產生 agent 端(Claude Desktop / Cursor / Cline …)可直接貼上的 mcpServers 設定。
 * 需要驗證的服務放一個明確的佔位符,提醒使用者要到 Tokens 頁產生 token 後替換,
 * 而不是複製出一份「看起來完整、實際連不上」的設定。
 */
export const TOKEN_PLACEHOLDER = '<YOUR_MCP_CENTER_TOKEN>'

export function buildAgentConfig({ name, url, requiresAuth = false }) {
  const server = { type: 'http', url }
  if (requiresAuth) server.headers = { Authorization: `Bearer ${TOKEN_PLACEHOLDER}` }
  return { mcpServers: { [name]: server } }
}
