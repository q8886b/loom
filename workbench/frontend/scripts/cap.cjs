const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

const OUT = '/tmp/loom_report_assets'
fs.mkdirSync(OUT, { recursive: true })

async function screenshot(page, name, opts = {}) {
  const file = path.join(OUT, name)
  await page.screenshot({ path: file, fullPage: false })
  console.log('saved', file)
  return file
}

async function waitGraph(page, extra = 1500) {
  await page.waitForTimeout(extra)
}

async function state(page) {
  return page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    return {
      density: s.densityLevel, activeNs: s.activeNs,
      cards: s.allCards.length, graph: s.graphNodes.length,
      selected: s.selectedId, viewMode: s.viewMode,
      focused: s.focused ? s.focused.id : null,
    }
  })
}

;(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' })
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })
  await page.goto('http://localhost:8888')
  await waitGraph(page, 2500)

  // 1. 视图 B：默认 gen 网格
  console.log('01 gen grid:', await state(page))
  await screenshot(page, '01_gen_grid.png')

  // 2. 选中 gen:1a（点卡片 tile）
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.onExpandCard('gen:1a')
  })
  await waitGraph(page)
  console.log('02 selected:', await state(page))
  await screenshot(page, '02_card_selected.png')

  // 3. 视图 C：聚焦模式（双击卡片）
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.onFocusCard('gen:1a')
  })
  await waitGraph(page, 2000)
  console.log('03 focused:', await state(page))
  await screenshot(page, '03_focus.png')

  // 4. 切到 llm 域
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.onExpandCard('llm')
  })
  await waitGraph(page, 2000)
  console.log('04 llm:', await state(page))
  await screenshot(page, '04_llm_grid.png')

  // 5. 切到 fin 域（大域）
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.onExpandCard('fin')
  })
  await waitGraph(page, 2500)
  console.log('05 fin:', await state(page))
  await screenshot(page, '05_fin_grid.png')

  // 6. 视图 A：L0 域 tile（点 L0 按钮）
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.setDensity(0)
  })
  await waitGraph(page)
  console.log('06 L0:', await state(page))
  await screenshot(page, '06_L0_domains.png')

  // 7. 视图 A：点 fin tile 进 fin 网格
  await page.evaluate(() => {
    const s = document.querySelector('#app').__vue_app__._instance.setupState
    s.onExpandCard('fin')
  })
  await waitGraph(page, 2500)
  console.log('07 fin from L0:', await state(page))
  await screenshot(page, '07_fin_from_tile.png')

  await browser.close()
})()
