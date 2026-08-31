import assert from 'node:assert/strict'
import { safeRedirectPath } from '../src/utils/redirect.js'

// 合法的同站路徑照原樣回傳
assert.equal(safeRedirectPath('/services/abc?tab=tools'), '/services/abc?tab=tools')
assert.equal(safeRedirectPath('/'), '/')
// 開放式重導向(open redirect)一律回 fallback
assert.equal(safeRedirectPath('//evil.example.com'), '/')
assert.equal(safeRedirectPath('/\\evil.example.com'), '/')
assert.equal(safeRedirectPath('https://evil.example.com'), '/')
assert.equal(safeRedirectPath('javascript:alert(1)'), '/')
assert.equal(safeRedirectPath('/ok bad'), '/')
assert.equal(safeRedirectPath('/ok\tbad'), '/')
// 避免登入後又回登入頁
assert.equal(safeRedirectPath('/login'), '/')
assert.equal(safeRedirectPath('/login?next=x'), '/')
// /setup 也是登入流程自己的頁面
assert.equal(safeRedirectPath('/setup'), '/')
// OAuth 同意頁必須能被記住,登入後才接得回授權流程
assert.equal(safeRedirectPath('/consent?rid=abc'), '/consent?rid=abc')
// 非字串 / 空值 / 自訂 fallback / 超長
assert.equal(safeRedirectPath(null), '/')
assert.equal(safeRedirectPath('', '/dashboard'), '/dashboard')
assert.equal(safeRedirectPath('/' + 'x'.repeat(3000)), '/')

console.log('redirect.test.mjs ALL PASS')
