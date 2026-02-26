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
  page.setDefaultTimeout(8000);

  // Go to board
  console.log('Opening board...');
  await page.goto(`${BOARD_URL}/boards/${BOARD_ID}`, { waitUntil: 'networkidle' });
  await sleep(2000);
  await page.keyboard.press('Escape'); // dismiss any dialog
  await sleep(1500);

  // Pause on the board view
  console.log('Board overview...');
  await sleep(2500);

  // Click a Done ticket (has the most info - subtract)
  console.log('Clicking subtract ticket...');
  const subtractTicket = page.locator('text=Fix reversed operands in subtract').first();
  await subtractTicket.click();
  await sleep(3000);

  // Scroll down in the detail panel to show all sections
  console.log('Scrolling detail panel...');
  await page.evaluate(() => {
    const panels = document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]');
    for (const p of panels) {
      if (p.scrollHeight > p.clientHeight && p.clientHeight > 200) {
        p.scrollTo({ top: 300, behavior: 'smooth' });
        return;
      }
    }
  });
  await sleep(2500);

  // Scroll more to show activity timeline
  await page.evaluate(() => {
    const panels = document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]');
    for (const p of panels) {
      if (p.scrollHeight > p.clientHeight && p.clientHeight > 200) {
        p.scrollTo({ top: 600, behavior: 'smooth' });
        return;
      }
    }
  });
  await sleep(2500);

  // Scroll back up
  await page.evaluate(() => {
    const panels = document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]');
    for (const p of panels) {
      if (p.scrollHeight > p.clientHeight && p.clientHeight > 200) {
        p.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
    }
  });
  await sleep(2000);

  // Close and click a Needs Review ticket (fibonacci - has code changes)
  console.log('Switching to fibonacci ticket...');
  await page.keyboard.press('Escape');
  await sleep(1000);

  const fibTicket = page.locator('text=Fix fibonacci off-by-one').first();
  await fibTicket.click();
  await sleep(3000);

  // Look for Review Changes / code revision button
  console.log('Looking for revision/code review...');
  const reviewBtn = page.locator('text=Review Changes').first();
  if (await reviewBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    console.log('Opening diff viewer...');
    await reviewBtn.click();
    await sleep(4000);

    // Scroll the diff
    await page.evaluate(() => {
      const diffArea = document.querySelector('[class*="diff"], [class*="code"], [class*="review"]');
      if (diffArea) diffArea.scrollTo({ top: 200, behavior: 'smooth' });
    });
    await sleep(2000);

    // Close diff
    await page.keyboard.press('Escape');
    await sleep(1000);
  }

  // Scroll detail panel to show verification evidence
  console.log('Showing verification evidence...');
  await page.evaluate(() => {
    const panels = document.querySelectorAll('[class*="overflow-y"], [class*="scroll"]');
    for (const p of panels) {
      if (p.scrollHeight > p.clientHeight && p.clientHeight > 200) {
        p.scrollTo({ top: 500, behavior: 'smooth' });
        return;
      }
    }
  });
  await sleep(3000);

  // Final pause
  await sleep(1500);

  const video = page.video();
  await context.close();
  const videoPath = await video?.path();
  console.log(`Done! Video: ${videoPath}`);
  await browser.close();
})();
