/**
 * 前端 i18n key 覆蓋:所有以字面字串呼叫的 t('a.b.c') 都必須同時存在於 zh-TW 與 en。
 * 漏 key 時 i18next 會把 key 原文顯示在畫面上(例如 "services.common.refresh"),
 * 這種錯誤 build 不會攔、只有使用者會看到 —— 所以在這裡攔。
 * 動態組出的 key(t(`x.${y}`))不在此檢查範圍。
 */
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')
const zh = JSON.parse(readFileSync(join(root, 'i18n/locales/zh-TW.json'), 'utf8'))
const en = JSON.parse(readFileSync(join(root, 'i18n/locales/en.json'), 'utf8'))

function lookup(dict, key) {
  let node = dict
  for (const part of key.split('.')) {
    if (node === null || typeof node !== 'object' || !(part in node)) return undefined
    node = node[part]
  }
  return node
}

// i18next 複數:t('x.count', { count }) 會解析成 x.count_one / x.count_other
function has(dict, key) {
  if (lookup(dict, key) !== undefined) return true
  return lookup(dict, `${key}_one`) !== undefined || lookup(dict, `${key}_other`) !== undefined
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (/\.(jsx?|tsx?)$/.test(name)) yield p
  }
}

const missing = []
let total = 0
for (const file of walk(root)) {
  const src = readFileSync(file, 'utf8')
  for (const m of src.matchAll(/\bt\(\s*'([a-zA-Z0-9_.]+)'/g)) {
    total++
    const key = m[1]
    if (!has(zh, key)) missing.push(`${key} (zh-TW) ← ${file.slice(root.length + 1)}`)
    if (!has(en, key)) missing.push(`${key} (en) ← ${file.slice(root.length + 1)}`)
  }
}
assert.ok(total > 500, `expected to find many t() calls, found ${total}`)
assert.deepEqual(missing, [], `missing i18n keys:\n  ${missing.join('\n  ')}`)
console.log(`i18nKeys.test.mjs ALL PASS (${total} static keys checked)`)
