const { chromium } = require('playwright')
async function main() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } })
  await page.goto('http://localhost:8888', { waitUntil: 'networkidle' })
  // 默认 gen 域：点第一张卡 → 聚焦（gen:1 是高度连接的 L4）
  await page.click('.card-list-item >> nth=0')
  await page.waitForSelector('.focus-btn', { timeout: 10000 })
  await page.click('.focus-btn')
  await page.waitForSelector('.vue-flow__node-card-focus-center', { timeout: 10000 })
  await page.waitForTimeout(800)
  const overlap = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll('.vue-flow__node')]
    const rects = nodes.map(n => {
      const r = n.getBoundingClientRect()
      return { id: n.dataset.id, x: r.x, y: r.y, w: r.width, h: r.height }
    })
    let bad = 0
    const pairs = []
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i], b = rects[j]
        const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
        const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
        if (ox > 4 && oy > 4) { bad++; if (pairs.length < 5) pairs.push([a.id, b.id]) }
      }
    }
    return { count: rects.length, bad, pairs }
  })
  console.log(`密集聚焦: ${overlap.count} 节点, 重叠对 ${overlap.bad}`, overlap.pairs)
  console.log(overlap.bad === 0 ? 'DENSE FOCUS PASSED' : 'DENSE FOCUS FAILED')
  await browser.close()
  process.exit(overlap.bad === 0 ? 0 : 1)
}
main().catch(e => { console.error(e); process.exit(1) })
