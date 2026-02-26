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
  page.setDefaultTimeout(10000);

  // Go to board
  console.log('Opening board...');
  await page.goto(`${BOARD_URL}/boards/${BOARD_ID}`, { waitUntil: 'networkidle' });
  await sleep(1500);
  await page.keyboard.press('Escape');
  await sleep(1000);

  // Brief board view
  await sleep(1500);

  // Click the planned ticket (fibonacci)
  console.log('Opening fibonacci ticket...');
  await page.click('text=Fix fibonacci off-by-one');
  await sleep(1500);

  // Hit Execute
  console.log('Executing...');
  const executeBtn = page.locator('button:has-text("Execute")').first();
  if (await executeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await executeBtn.click();
    await sleep(1500);
  } else {
    console.log('No Execute button found!');
  }

  // Close detail
  await page.keyboard.press('Escape');
  await sleep(500);

  // Open Debug panel to watch live logs
  console.log('Opening debug panel...');
  const debugBtn = page.locator('button:has-text("Debug")').first();
  await debugBtn.click();
  await sleep(2000);

  // Watch debug logs stream in, auto-scroll to bottom every few seconds
  for (let i = 0; i < 20; i++) {
    await sleep(2000);
    if (i % 4 === 0) console.log(`  ${(i + 1) * 2}s - following logs...`);
    await page.evaluate(() => {
      document.querySelectorAll('[class*="overflow"], pre, code, [class*="log"], [class*="terminal"], [class*="scroll"], [role="log"]').forEach(el => {
        if (el.scrollHeight > el.clientHeight) {
          el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
        }
      });
    });
  }

  // Close debug
  console.log('Closing debug...');
  await page.keyboard.press('Escape');
  await sleep(1000);

  // Click the ticket to show agent activity in detail panel
  console.log('Showing ticket detail with agent results...');
  const ticket = page.locator('text=Fix fibonacci').first();
  if (await ticket.isVisible({ timeout: 2000 }).catch(() => false)) {
    await ticket.click();
    await sleep(2000);

    // Scroll through detail to show agent work
    for (const pos of [300, 600, 900, 1200]) {
      await page.evaluate((p) => {
        document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]').forEach(el => {
          if (el.scrollHeight > el.clientHeight && el.clientHeight > 200) {
            el.scrollTo({ top: p, behavior: 'smooth' });
          }
        });
      }, pos);
      await sleep(1500);
    }
  }

  // Final board view
  console.log('Final board...');
  await page.keyboard.press('Escape');
  await sleep(2000);

  const video = page.video();
  await context.close();
  const videoPath = await video?.path();
  console.log(`Done! Video: ${videoPath}`);
  await browser.close();
})();
