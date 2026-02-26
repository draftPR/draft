import { chromium } from 'playwright';

const BOARD_URL = 'http://localhost:5173';
const BOARD_ID = '223a0e11-6bdb-4a92-949e-2f37284f93a8';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: './demo-videos/', size: { width: 1440, height: 900 } },
  });

  const page = await context.newPage();
  page.setDefaultTimeout(5000);

  // Helper: dismiss any overlay/dialog
  async function dismissDialogs() {
    // Try Escape key
    await page.keyboard.press('Escape');
    await sleep(500);
    // Click overlay if still there
    const overlay = page.locator('[data-slot="dialog-overlay"], [class*="dialog-overlay"]').first();
    if (await overlay.isVisible({ timeout: 500 }).catch(() => false)) {
      await overlay.click({ force: true });
      await sleep(500);
    }
  }

  // 1. Go directly to the board
  console.log('Opening board...');
  await page.goto(`${BOARD_URL}/boards/${BOARD_ID}`, { waitUntil: 'networkidle' });
  await sleep(2000);

  // Dismiss any startup dialog
  await dismissDialogs();
  await sleep(1000);

  // Take a screenshot to debug what's visible
  await page.screenshot({ path: './demo-videos/debug-board.png' });
  console.log('Board loaded, debug screenshot saved');

  // 2. Pan across columns slowly
  console.log('Panning across columns...');
  // Try scrolling the main content area
  await page.evaluate(() => {
    const scrollable = document.querySelector('[class*="overflow-x"]') || 
                       document.querySelector('main') ||
                       document.documentElement;
    if (scrollable) scrollable.scrollTo({ left: 400, behavior: 'smooth' });
  });
  await sleep(2000);
  await page.evaluate(() => {
    const scrollable = document.querySelector('[class*="overflow-x"]') || 
                       document.querySelector('main') ||
                       document.documentElement;
    if (scrollable) scrollable.scrollTo({ left: 0, behavior: 'smooth' });
  });
  await sleep(1500);

  // 3. Click a ticket - look for ticket titles
  console.log('Opening ticket detail...');
  const ticketTitles = [
    'Fix power function',
    'Fix reversed operands',
    'Fix subtract',
    'Fix average',
    'Fix fibonacci',
    'Fix factorial',
    'Fix is_prime',
  ];
  let ticketClicked = false;
  for (const title of ticketTitles) {
    const el = page.locator(`text=${title}`).first();
    if (await el.isVisible({ timeout: 500 }).catch(() => false)) {
      await el.click();
      ticketClicked = true;
      console.log(`  Clicked: ${title}`);
      break;
    }
  }
  if (!ticketClicked) {
    // Fallback: click any visible text that looks like a ticket
    console.log('  No ticket found by name, trying generic...');
    await page.screenshot({ path: './demo-videos/debug-no-ticket.png' });
  }
  await sleep(3000);

  // 4. Scroll detail panel
  console.log('Scrolling detail panel...');
  await page.evaluate(() => {
    const panels = document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]');
    for (const p of panels) {
      if (p.scrollHeight > p.clientHeight && p.clientHeight > 200) {
        p.scrollTo({ top: 400, behavior: 'smooth' });
        break;
      }
    }
  });
  await sleep(2000);
  await page.evaluate(() => {
    const panels = document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]');
    for (const p of panels) {
      if (p.scrollHeight > p.clientHeight && p.clientHeight > 200) {
        p.scrollTo({ top: 0, behavior: 'smooth' });
        break;
      }
    }
  });
  await sleep(1500);

  // 5. Close detail
  console.log('Closing detail...');
  await page.keyboard.press('Escape');
  await sleep(1500);

  // 6. Click Needs Review ticket (subtract)
  console.log('Looking for Needs Review ticket...');
  const subtractTicket = page.locator('text=subtract').first();
  if (await subtractTicket.isVisible({ timeout: 1000 }).catch(() => false)) {
    await subtractTicket.click();
    await sleep(2500);

    // Try Review Changes button
    const reviewBtn = page.locator('text=Review Changes').first();
    if (await reviewBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      console.log('Opening diff viewer...');
      await reviewBtn.click();
      await sleep(4000);
      await page.keyboard.press('Escape');
      await sleep(1500);
    }

    await page.keyboard.press('Escape');
    await sleep(1000);
  }

  // 7. Goals dialog
  console.log('Looking for Goals button...');
  const goalsBtn = page.locator('button:has-text("Goals"), [aria-label*="goal" i]').first();
  if (await goalsBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await goalsBtn.click();
    await sleep(3000);
    await page.keyboard.press('Escape');
    await sleep(1000);
  }

  // 8. Final board view pause
  console.log('Final board view...');
  await sleep(2000);

  // Close and save video
  const video = page.video();
  await context.close();
  const videoPath = await video?.path();
  console.log(`Done! Video saved: ${videoPath}`);
  await browser.close();
})();
