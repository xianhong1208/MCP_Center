/**
 * 顯示用格式化(純函式,無 React 相依)
 */

/**
 * 毫秒 → 人看得懂的字串。
 *   842      → "842 ms"
 *   1480     → "1.5 s"
 *   60226    → "60.2 s"
 *   125000   → "2.1 min"
 * 原始 "60226ms" 對使用者毫無意義 —— 這類數字要先翻譯成人的尺度。
 */
export function formatMs(ms) {
  if (ms == null || Number.isNaN(Number(ms))) return ''
  const n = Number(ms)
  if (n < 1000) return `${Math.round(n)} ms`
  if (n < 60_000) return `${(n / 1000).toFixed(1)} s`
  if (n < 3_600_000) return `${(n / 60_000).toFixed(1)} min`
  return `${(n / 3_600_000).toFixed(1)} h`
}

/**
 * 後端時間字串 → Date。
 * 後端回 'YYYY-MM-DD HH:MM:SS'(伺服器本地時間,無時區標記);把空白換成 T 讓
 * 所有瀏覽器都能解析。瀏覽器與伺服器同時區時結果正確(內網部署的常態)。
 */
export function parseServerDate(value) {
  if (!value) return null
  const d = new Date(typeof value === 'string' ? value.replace(' ', 'T') : value)
  return Number.isNaN(d.getTime()) ? null : d
}

/**
 * 相對時間拆解 → { key, n },由呼叫端以 i18n 翻譯(common.relative.<key>)。
 * 拆成資料而不直接回字串,是為了讓純函式可在 node 下測、又不用把 i18n 拉進 utils。
 */
export function relativeTimeParts(value, now = Date.now()) {
  const d = parseServerDate(value)
  if (!d) return null
  const seconds = Math.max(0, Math.round((now - d.getTime()) / 1000))
  if (seconds < 45) return { key: 'justNow', n: seconds }
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return { key: 'minutesAgo', n: minutes }
  const hours = Math.round(minutes / 60)
  if (hours < 24) return { key: 'hoursAgo', n: hours }
  return { key: 'daysAgo', n: Math.round(hours / 24) }
}

/**
 * 後端時間字串 → 本地可讀日期時間(如 "2026/9/30 17:22")。無法解析時回原字串。
 */
export function formatDateTime(value) {
  const d = parseServerDate(value)
  if (!d) return value || ''
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
