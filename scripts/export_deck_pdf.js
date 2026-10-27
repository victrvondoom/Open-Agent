// Export docs/deck.html to docs/deck.pdf (one slide per page, numbers from the embedded
// deck-data block that `python3 -m payproof.bench` regenerates). Needs Playwright + Chromium.
// Usage: node scripts/export_deck_pdf.js
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const root = path.resolve(__dirname, "..");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("file://" + path.join(root, "docs", "deck.html"));
  await page.waitForTimeout(500);
  if (errors.length) throw new Error("deck has script errors: " + errors.join("; "));
  if (!(await page.textContent("#d-demo-title")).includes("$")) throw new Error("deck data did not render");
  await page.pdf({ path: path.join(root, "docs", "deck.pdf"), width: "1280px", height: "720px", printBackground: true, preferCSSPageSize: true });
  await browser.close();
  console.log("wrote docs/deck.pdf");
})();
