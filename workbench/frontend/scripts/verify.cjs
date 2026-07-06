const { chromium } = require('playwright')

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
  await page.goto('http://localhost:8888')
  await page.waitForTimeout(2500)

  // 视图 B: gen 网格
  const gridInfo = await page.evaluate(() => {
    const grid = document.querySelector('.card-grid')
    if (!grid) return { found: false }
    const rect = grid.getBoundingClientRect()
    const tiles = [...grid.querySelectorAll('.card-tile')]
    const groups = [...document.querySelectorAll('.card-group')]
    const cs = getComputedStyle(grid)
    return {
      found: true,
      cols: cs.gridTemplateColumns,
      gap: cs.gap,
      gridRect: { w: Math.round(rect.width), h: Math.round(rect.height) },
      tileCount: tiles.length,
      groupCount: groups.length,
      groupLabels: groups.map(g => g.querySelector('.group-key')?.textContent?.trim()),
      firstTileRect: tiles[0] ? (() => { const r = tiles[0].getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) } })() : null,
    }
  })
  console.log('View B gen grid DOM:', JSON.stringify(gridInfo, null, 2))

  // 视图 A: L0 域 tile
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.setDensity(0)
  })
  await page.waitForTimeout(800)
  const domainInfo = await page.evaluate(() => {
    const grid = document.querySelector('.domain-grid')
    if (!grid) return { found: false }
    const tiles = [...grid.querySelectorAll('.domain-tile')]
    const cs = getComputedStyle(grid)
    return {
      found: true,
      cols: cs.gridTemplateColumns,
      tileCount: tiles.length,
      labels: tiles.map(t => ({
        name: t.querySelector('.dt-name')?.textContent?.trim(),
        count: t.querySelector('.dt-count')?.textContent?.trim(),
      })),
    }
  })
  console.log('View A domains DOM:', JSON.stringify(domainInfo, null, 2))

  await browser.close()
})()
