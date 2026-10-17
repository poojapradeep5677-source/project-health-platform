/** Browser-level smoke for version-007.
 *
 * Runs with a real Flask backend and Vite web app, an actual Java ZIP upload,
 * live persisted class predictions, file-details drawer, and PDF download.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const ROOT = path.resolve(import.meta.dirname, '../..');
const ARCHIVE = path.join(ROOT, 'data', 'ecommerce-order-engine-v1.zip');
const OUT = path.join(ROOT, 'frontend', 'e2e-artifacts');
const ORIGIN = process.env.E2E_ORIGIN || 'http://127.0.0.1:5173';
fs.mkdirSync(OUT, { recursive: true });
assert.ok(fs.statSync(ARCHIVE).size > 1000, 'Java sample archive missing');

const browser = await chromium.launch({ headless: true });
const errors = [];

try {
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.on('pageerror', err => errors.push(err.message));

  await page.goto(ORIGIN + '/upload', { waitUntil: 'domcontentloaded' });
  await page.getByText('Java Project ZIP Archive Ingestion').waitFor({ timeout: 30000 });
  await page.locator('[data-testid="zip-file-input"]').setInputFiles(ARCHIVE);
  await page.getByPlaceholder('e.g., E-Commerce Order Engine').fill('Version-007 Browser E2E');
  await page.getByRole('button', { name: 'Upload & Analyze Project' }).click();
  await page.getByText(/Analysis Completed —/).waitFor({ timeout: 90000 });
  await page.screenshot({ path: path.join(OUT, '01-upload-success.png'), fullPage: true });
  console.log('PASS: Browser Java ZIP upload and analysis');

  await page.getByRole('button', { name: 'Inspect File Metrics' }).click();
  await page.waitForURL('**/analysis', { timeout: 30000 });
  await page.getByText('OrderProcessor.java').first().waitFor({ timeout: 30000 });
  await page.getByText('OrderProcessor.java').first().click();
  await page.getByText(/Java Class-Level Metrics & ML Risk/).waitFor({ timeout: 30000 });
  const details = page.getByRole('dialog');
  await details.getByText(/Class-Level Metrics/).waitFor();
  assert.ok((await details.getByText(/WMC proxy/).count()) > 0);
  await page.screenshot({ path: path.join(OUT, '02-class-predictions.png'), fullPage: true });
  console.log('PASS: File-detail drawer shows class-wise LOC and WMC risk');

  await page.goto(ORIGIN + '/reports', { waitUntil: 'domcontentloaded' });
  const pdfButton = page.getByRole('button', { name: 'Download Official PDF Report' });
  await pdfButton.waitFor({ timeout: 30000 });
  const downloadPromise = page.waitForEvent('download', { timeout: 45000 });
  await pdfButton.click();
  const download = await downloadPromise;
  assert.ok(download.suggestedFilename().endsWith('.pdf'));
  const filePath = await download.path();
  assert.ok(fs.statSync(filePath).size > 1500, 'PDF report is unexpectedly small');
  console.log('PASS: User-triggered PDF download is nonempty');

  await page.goto(ORIGIN + '/', { waitUntil: 'domcontentloaded' });
  await page.getByText('Version-007 Browser E2E').first().waitFor({ timeout: 30000 });
  await page.screenshot({ path: path.join(OUT, '03-dashboard.png'), fullPage: true });
  console.log('PASS: Dashboard renders uploaded project');

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const phone = await mobileContext.newPage();
  phone.on('pageerror', err => errors.push(err.message));
  await phone.goto(ORIGIN + '/analysis', { waitUntil: 'domcontentloaded' });
  await phone.getByText('OrderProcessor.java').first().waitFor({ timeout: 30000 });
  await phone.screenshot({ path: path.join(OUT, '04-mobile-analysis.png'), fullPage: true });
  console.log('PASS: Mobile analysis page renders without JS errors');

  assert.deepEqual(errors, [], 'Browser page errors: ' + errors.join(' | '));
  console.log('BROWSER E2E PASSED');
} finally {
  await browser.close();
}
