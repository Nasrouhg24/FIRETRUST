import { test, expect } from '@playwright/test'

test('explore opens on a world view with every region outlined and clickable', async ({ page }) => {
  test.setTimeout(90000)
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: 'Explore' }).click()
  await expect(page.getByRole('button', { name: 'All regions' })).toHaveAttribute('aria-pressed', 'true')
  await page.waitForTimeout(800)
  await page.screenshot({ path: '../artifacts/explore-world.png', fullPage: false })
  // choosing a region from the dropdown leaves the world view and updates the heading text
  await page.getByRole('combobox', { name: 'Region' }).selectOption('chile')
  await expect(page.getByRole('button', { name: 'All regions' })).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByText(/pass over Chile/)).toBeVisible()
  await page.getByRole('button', { name: 'All regions' }).click()
  await expect(page.getByRole('button', { name: 'All regions' })).toHaveAttribute('aria-pressed', 'true')
})
