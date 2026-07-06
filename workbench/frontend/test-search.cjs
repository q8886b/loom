const { chromium } = require('playwright-core')
const path = require('path')

const CHROMIUM_PATH = path.join(
  process.env.HOME,
  'Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
)

;(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM_PATH })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

  const errors = []
  page.on('pageerror', err => errors.push(err.message))

  await page.goto('http://127.0.0.1:8888', { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)

  // Test search
  console.log('=== Search test ===')
  const searchInput = page.locator('.search input')
  await searchInput.fill('康德')
  await searchInput.press('Enter')
  await page.waitForTimeout(1500)

  const searchPanel = await page.locator('.search-panel').isVisible().catch(() => false)
  console.log(`  Search panel visible: ${searchPanel}`)
  const searchItems = await page.locator('.search-item').count()
  console.log(`  Search results: ${searchItems}`)

  if (searchItems > 0) {
    const firstResult = await page.locator('.search-item').first().textContent()
    console.log(`  First result: "${firstResult.trim().substring(0, 60)}"`)
    // Click first result
    await page.locator('.search-item').first().click()
    await page.waitForTimeout(1000)
    const selected = await page.locator('.card-node.selected').count()
    console.log(`  After click result: selected=${selected}`)
  }

  // Close search by clicking elsewhere
  await page.locator('.brand').click()
  await page.waitForTimeout(500)

  // Test search with empty/short query
  console.log('\n=== Search edge cases ===')
  await searchInput.fill('a')
  await searchInput.press('Enter')
  await page.waitForTimeout(500)
  const shortPanel = await page.locator('.search-panel').isVisible().catch(() => false)
  console.log(`  Single char search panel: ${shortPanel} (should be false)`)

  // Test search with Chinese
  await searchInput.fill('交易')
  await searchInput.press('Enter')
  await page.waitForTimeout(1500)
  const cnResults = await page.locator('.search-item').count()
  console.log(`  "交易" results: ${cnResults}`)

  if (errors.length) {
    console.log('\n=== Page Errors ===')
    ;[...new Set(errors)].slice(0, 5).forEach(e => console.log(`  ${e.substring(0, 120)}`))
  } else {
    console.log('\nNo page errors.')
  }

  await browser.close()
  console.log('Done.')
})()
