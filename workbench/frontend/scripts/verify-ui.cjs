/* UI 端到端冒烟：书籍路径 + 阅读进度 + 聚焦不堆叠 + 漫游 */
const { chromium } = require('playwright')

const BASE = 'http://localhost:8888'

async function main() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } })
  const fail = (msg) => { console.error('FAIL:', msg); process.exitCode = 1 }
  const ok = (msg) => console.log('OK:', msg)

  await page.goto(BASE, { waitUntil: 'networkidle' })

  // 1. 点 fin 域，验证加载速度 + 书籍区出现
  let t0 = Date.now()
  await page.click('.ns-item:has-text("fin")')
  await page.waitForSelector('.book-list .book-item', { timeout: 15000 })
  const loadMs = Date.now() - t0
  const bookCount = await page.locator('.book-list .book-item').count()
  ok(`fin 域加载 ${loadMs}ms，书籍条目 ${bookCount}`)
  if (loadMs > 3000) fail(`fin 域加载过慢: ${loadMs}ms`)
  if (bookCount < 10) fail(`书籍条目过少: ${bookCount}`)

  // 等图谱出来（summary 模式）
  await page.waitForSelector('.vue-flow__node', { timeout: 15000 })

  // 2. 点第一本书 → 列表与图谱过滤到该书
  await page.click('.book-list .book-item >> nth=1')
  await page.waitForFunction(
    () => !document.querySelector('.card-list-header')?.textContent.includes('8174'),
    { timeout: 10000 },
  )
  const header = await page.textContent('.card-list-header')
  ok(`书籍视图列表头: ${header.trim()}`)
  if (header.includes('8174')) fail('书籍过滤未生效')
  await page.waitForTimeout(1200)
  const nodeCountAfterBook = await page.locator('.vue-flow__node').count()
  ok(`书籍视图图谱节点数: ${nodeCountAfterBook}`)
  if (nodeCountAfterBook === 0) fail('书籍视图为空图（summary 裁剪问题）')

  // 3. 阅读进度：读两张卡 → 出现已读样式与"继续阅读"
  await page.click('.card-list-item >> nth=0')
  await page.waitForSelector('.card header .layer-tag', { timeout: 10000 })
  await page.click('.card-list-item >> nth=1')
  await page.waitForTimeout(400)
  const readCount = await page.locator('.card-list-item.read').count()
  const hasContinue = await page.locator('.continue-btn').count()
  ok(`已读样式 ${readCount} 条，继续阅读按钮 ${hasContinue ? '有' : '无'}`)
  if (readCount < 2) fail('已读样式未生效')

  // 刷新后进度仍在（刷新回到默认 gen 域，需重新进入 fin → 同一本书）
  await page.reload({ waitUntil: 'networkidle' })
  await page.click('.ns-item:has-text("fin")')
  await page.waitForSelector('.book-list .book-item', { timeout: 15000 })
  await page.click('.book-list .book-item >> nth=1')
  await page.waitForFunction(
    () => !document.querySelector('.card-list-header')?.textContent.includes('8174'),
    { timeout: 10000 },
  )
  await page.waitForTimeout(500)
  const readAfterReload = await page.locator('.card-list-item.read').count()
  ok(`刷新后已读 ${readAfterReload} 条`)
  if (readAfterReload < 2) fail('阅读进度未持久化')

  // 4. 聚焦：点一张卡 → 聚焦按钮 → 检查邻居不重叠
  await page.click('.card-list-item >> nth=0')
  await page.waitForSelector('.focus-btn', { timeout: 10000 })
  await page.click('.focus-btn')
  await page.waitForSelector('.vue-flow__node-card-focus-center', { timeout: 10000 })
  await page.waitForTimeout(600)
  const overlap = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll('.vue-flow__node')]
    const rects = nodes.map(n => {
      const r = n.getBoundingClientRect()
      return { id: n.dataset.id, x: r.x, y: r.y, w: r.width, h: r.height }
    })
    let bad = 0
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i], b = rects[j]
        const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
        const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
        if (ox > 4 && oy > 4) bad++
      }
    }
    return { count: rects.length, bad }
  })
  ok(`聚焦模式 ${overlap.count} 节点，重叠对 ${overlap.bad}`)
  if (overlap.bad > 0) fail(`聚焦模式仍有 ${overlap.bad} 对节点重叠`)

  // 5. 漫游：聚焦模式单击邻居 → 中心切换
  const centerBefore = await page.evaluate(() =>
    document.querySelector('.vue-flow__node-card-focus-center')?.dataset.id)
  const neighbor = page.locator('.vue-flow__node-card:not(.vue-flow__node-card-focus-center)').first()
  await neighbor.click()
  await page.waitForTimeout(900)
  const centerAfter = await page.evaluate(() =>
    document.querySelector('.vue-flow__node-card-focus-center')?.dataset.id)
  ok(`漫游: ${centerBefore} → ${centerAfter}`)
  if (!centerAfter || centerAfter === centerBefore) fail('单击邻居未切换中心（漫游失败）')

  await browser.close()
  console.log(process.exitCode ? 'SMOKE FAILED' : 'SMOKE PASSED')
}

main().catch(e => { console.error(e); process.exit(1) })
