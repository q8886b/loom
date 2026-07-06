const { chromium } = require('playwright')

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
  await page.goto('http://localhost:8888')
  await page.waitForTimeout(2500)

  const info = await page.evaluate(() => {
    const view = document.querySelector('.view-grid')
    const scroll = document.querySelector('.grid-scroll')
    const groups = [...document.querySelectorAll('.card-group')]
    return {
      viewRect: view ? (() => { const r = view.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) } })() : null,
      scrollRect: scroll ? (() => { const r = scroll.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) } })() : null,
      scrollHeight: scroll ? scroll.scrollHeight : null,
      groups: groups.map(g => ({
        label: g.querySelector('.group-key')?.textContent?.trim(),
        count: g.querySelector('.group-count')?.textContent?.trim(),
        tileCount: g.querySelectorAll('.card-tile').length,
      })),
    }
  })
  console.log(JSON.stringify(info, null, 2))

  await page.screenshot({ path: '/tmp/loom_report_assets/01_gen_grid.png', fullPage: false })
  console.log('saved 01_gen_grid.png')
  await browser.close()
})()
