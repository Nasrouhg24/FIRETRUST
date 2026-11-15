import { test, expect } from '@playwright/test'

test('accessibility basics, tablet layout and large-region timing', async ({ page }) => {
  test.setTimeout(180000)
  await page.setViewportSize({ width: 820, height: 1100 })
  await page.goto('/')
  const report: Record<string, unknown> = {}
  for (const tab of ['Discover', 'Explore', 'Compare', 'Calendar', 'Evidence']) {
    await page.getByRole('navigation').getByRole('button', { name: tab }).click()
    await page.waitForLoadState('networkidle')
    const unnamed = await page.evaluate(() => [...document.querySelectorAll('button, a[href], select, input, [role=img], svg[role=img]')].filter(el => {
      const e = el as HTMLElement
      if (e.closest('.leaflet-container')) return false
      const label = e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent?.trim() || (e.id && document.querySelector(`label[for="${e.id}"]`)?.textContent) || e.closest('label')?.textContent?.trim()
      return !label
    }).map(e => e.outerHTML.slice(0, 120)))
    expect(unnamed, `${tab}: controls without an accessible name`).toEqual([])
    expect(await page.evaluate(() => document.querySelectorAll('h1').length), `${tab}: exactly one h1`).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${tab}: no horizontal overflow at tablet width`).toBe(true)
  }
  // Keyboard: skip link is first, focus is visible, navigation is reachable
  await page.goto('/')
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => document.activeElement?.textContent)).toBe('Skip to content')
  await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab')
  const focused = await page.evaluate(() => { const e = document.activeElement as HTMLElement; return { text: e.textContent, outline: getComputedStyle(e).outlineStyle } })
  expect(focused.outline).not.toBe('none')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('What the satellites recorded')
  // Largest region: loading state appears, then data
  const started = Date.now()
  await page.getByRole('combobox', { name: 'Region' }).selectOption('zambia')
  await expect(page.getByRole('status').first()).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0, { timeout: 60000 })
  report.zambia_explore_ms = Date.now() - started
  const t2 = Date.now()
  await page.getByRole('navigation').getByRole('button', { name: 'Compare' }).click()
  await expect(page.getByRole('img', { name: /Monthly active cell-days/ })).toBeVisible({ timeout: 60000 })
  report.zambia_compare_ms = Date.now() - t2
  await expect(page.getByText('No uncertainty band in Zambia.')).toBeVisible()
  const t3 = Date.now()
  await page.getByRole('navigation').getByRole('button', { name: 'Calendar' }).click()
  await expect(page.locator('.heatmap')).toBeVisible({ timeout: 60000 })
  report.zambia_calendar_ms_cached = Date.now() - t3
  await page.screenshot({ path: '../artifacts/ui/tablet-zambia-calendar.png', fullPage: true })
  console.log('AUDIT', JSON.stringify(report))
})
