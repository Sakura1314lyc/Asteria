'use strict';

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = (process.env.QA_BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const MODE = process.argv.includes('--record')
  ? 'record'
  : process.argv.includes('--rehearse')
    ? 'rehearse'
    : 'explore';
const OUTPUT_DIR = path.resolve(
  process.env.QA_OUTPUT_DIR || path.join(__dirname, '..', 'artifacts', 'ui-demo')
);

async function injectOverlays(page) {
  await page.evaluate(() => {
    if (!document.getElementById('demo-cursor')) {
      const cursor = document.createElement('div');
      cursor.id = 'demo-cursor';
      cursor.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="#172431" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
      cursor.style.cssText = 'position:fixed;z-index:999999;pointer-events:none;width:24px;height:24px;left:0;top:0;transition:left .1s,top .1s;filter:drop-shadow(1px 1px 2px rgba(0,0,0,.3))';
      document.body.appendChild(cursor);
      document.addEventListener('mousemove', (event) => {
        cursor.style.left = `${event.clientX}px`;
        cursor.style.top = `${event.clientY}px`;
      });
    }
    if (!document.getElementById('demo-subtitle')) {
      const bar = document.createElement('div');
      bar.id = 'demo-subtitle';
      bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:999998;text-align:center;padding:12px 24px;background:rgba(15,25,35,.84);color:white;font:500 16px "Segoe UI",sans-serif;letter-spacing:.2px;opacity:0;transition:opacity .25s;pointer-events:none';
      document.body.appendChild(bar);
    }
  });
}

async function showSubtitle(page, text) {
  await page.evaluate((value) => {
    const bar = document.getElementById('demo-subtitle');
    if (!bar) return;
    bar.textContent = value;
    bar.style.opacity = value ? '1' : '0';
  }, text);
  await page.waitForTimeout(text ? 900 : 300);
}

async function ensureVisible(page, locator, label) {
  const element = typeof locator === 'string' ? page.locator(locator).first() : locator;
  const visible = await element.isVisible().catch(() => false);
  if (visible) {
    console.log(`REHEARSAL OK: ${label}`);
    return true;
  }
  const found = await page.evaluate(() =>
    Array.from(document.querySelectorAll('button, input, select, textarea, a'))
      .filter((element) => element.offsetParent !== null)
      .map((element) => `${element.tagName} "${element.textContent?.trim().slice(0, 36) || ''}"`)
  );
  console.error(`REHEARSAL FAIL: ${label}`);
  console.error(`Visible controls:\n  ${found.join('\n  ')}`);
  return false;
}

async function moveAndClick(page, locator, label, postClickDelay = 1400) {
  const element = typeof locator === 'string' ? page.locator(locator).first() : locator;
  if (!(await ensureVisible(page, element, label))) return false;
  await element.scrollIntoViewIfNeeded();
  const box = await element.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 });
    await page.waitForTimeout(450);
  }
  await element.click();
  await page.waitForTimeout(postClickDelay);
  return true;
}

async function dumpPage(page, label) {
  const fields = await page.evaluate(() =>
    Array.from(document.querySelectorAll('input, select, textarea, button, a, [contenteditable]'))
      .filter((element) => element.offsetParent !== null)
      .map((element) => ({
        tag: element.tagName,
        type: element.type || '',
        name: element.name || '',
        placeholder: element.placeholder || '',
        text: element.textContent?.trim().slice(0, 50) || '',
        role: element.getAttribute('role') || ''
      }))
  );
  console.log(`\nEXPLORE ${label}\n${JSON.stringify(fields, null, 2)}`);
  const name = label
    .replace('/app/projects/:projectId/runs/:runId', 'run')
    .replace('/app/projects/:projectId', 'project')
    .replace('/app', 'dashboard');
  await page.screenshot({
    path: path.join(OUTPUT_DIR, `${name}.png`),
    fullPage: true
  });
}

async function projectRoutes() {
  if (process.env.QA_PROJECT_URL) {
    return {
      projectUrl: process.env.QA_PROJECT_URL,
      runUrl: process.env.QA_RUN_URL || ''
    };
  }
  const response = await fetch(`${BASE_URL}/projects`);
  if (!response.ok) throw new Error(`Cannot read projects: HTTP ${response.status}`);
  const projects = await response.json();
  const project = projects[0];
  if (!project) return { projectUrl: '', runUrl: '' };
  const projectUrl = `${BASE_URL}/app/projects/${project.id}`;
  const runId = project.runs?.[0]?.id;
  return {
    projectUrl,
    runUrl: runId ? `${projectUrl}/runs/${runId}` : ''
  };
}

async function navigate(page, url) {
  await page.goto(url, { waitUntil: 'networkidle' });
  await injectOverlays(page);
}

async function explore(page, routes) {
  await navigate(page, `${BASE_URL}/app`);
  await dumpPage(page, '/app');
  await page.waitForTimeout(1500);
  await page.screenshot({
    path: process.env.QA_DASHBOARD_SCREENSHOT || path.join(OUTPUT_DIR, 'dashboard-stable.png'),
    fullPage: true
  });
  const firstProject = page.locator('.research-ledger__row').first();
  if (await firstProject.isVisible().catch(() => false)) {
    await firstProject.hover();
    await page.waitForTimeout(220);
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'dashboard-hover.png'),
      fullPage: true
    });
  }
  if (routes.projectUrl) {
    await navigate(page, routes.projectUrl);
    await dumpPage(page, '/app/projects/:projectId');
    if (process.env.QA_LIFECYCLE === '1') {
      await exploreLifecycleControls(page, routes);
    }
  }
  if (routes.runUrl) {
    await navigate(page, routes.runUrl);
    await dumpPage(page, '/app/projects/:projectId/runs/:runId');
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await navigate(page, `${BASE_URL}/app`);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, 'mobile-dashboard.png'),
    fullPage: true
  });
  await page.getByRole('button', { name: '打开导航' }).click();
  await page.waitForTimeout(250);
  await page.screenshot({
    path: path.join(OUTPUT_DIR, 'mobile-navigation.png'),
    fullPage: false
  });
  if (process.env.QA_LIFECYCLE === '1' && routes.projectUrl) {
    await navigate(page, routes.projectUrl);
    const edit = page.getByRole('button', { name: '编辑项目' });
    if (await edit.isEnabled().catch(() => false)) {
      await edit.click();
      await page.screenshot({
        path: path.join(OUTPUT_DIR, 'mobile-project-edit.png'),
        fullPage: false
      });
      const mobileDialogFits = await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      );
      if (!mobileDialogFits) {
        throw new Error('Lifecycle modal overflows the mobile viewport');
      }
      await page.getByRole('button', { name: '关闭' }).click();
    }
  }
}

async function exploreLifecycleControls(page, routes) {
  const edit = page.getByRole('button', { name: '编辑项目' });
  if (await edit.isEnabled().catch(() => false)) {
    await edit.click();
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'project-edit.png'),
      fullPage: false
    });
    await page.getByRole('button', { name: '删除项目' }).click();
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'project-delete-confirmation.png'),
      fullPage: false
    });
    await page.getByRole('button', { name: '关闭' }).click();
  }

  const reviseProtocol = page.getByRole('button', { name: '修订方案' });
  if (await reviseProtocol.isEnabled().catch(() => false)) {
    await reviseProtocol.click();
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'protocol-edit.png'),
      fullPage: false
    });
    await page.getByRole('button', { name: '关闭' }).click();
  }

  await navigate(page, `${routes.projectUrl}/documents`);
  const deleteDocument = page.getByRole('button', { name: /^删除全文 / }).first();
  if (await deleteDocument.isEnabled().catch(() => false)) {
    await deleteDocument.click();
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'document-delete-confirmation.png'),
      fullPage: false
    });
    await page.getByRole('button', { name: '取消' }).click();
  }

  await navigate(page, `${routes.projectUrl}/chat`);
  const deleteConversation = page
    .getByRole('button', { name: /^删除对话 / })
    .first();
  if (await deleteConversation.isEnabled().catch(() => false)) {
    await deleteConversation.click();
    await page.screenshot({
      path: path.join(OUTPUT_DIR, 'conversation-delete-confirmation.png'),
      fullPage: false
    });
    await page.getByRole('button', { name: '取消' }).click();
  }

  if (routes.runUrl) {
    await navigate(page, routes.runUrl);
    const deleteRun = page.getByRole('button', { name: '删除运行' });
    if (await deleteRun.isEnabled().catch(() => false)) {
      await deleteRun.click();
      await page.screenshot({
        path: path.join(OUTPUT_DIR, 'run-delete-confirmation.png'),
        fullPage: false
      });
      await page.getByRole('button', { name: '取消' }).click();
    }
  }
}

async function rehearse(page, routes) {
  let passed = true;
  await navigate(page, `${BASE_URL}/app`);
  passed = (await ensureVisible(page, '.dashboard-hero h1', 'dashboard thesis')) && passed;
  passed = (await ensureVisible(page, '.research-ledger__row', 'recent project row')) && passed;
  if (routes.projectUrl) {
    await navigate(page, routes.projectUrl);
    passed = (await ensureVisible(page, '.project-masthead h1', 'project identity')) && passed;
    passed = (await ensureVisible(page, '.research-spine', 'research evidence spine')) && passed;
    passed = (await ensureVisible(page, '.run-list__item', 'run history entry')) && passed;
    passed = (await ensureVisible(page, '.project-manage-line', 'project lifecycle controls')) && passed;
    passed = (await ensureVisible(page, '.project-activity', 'project revision ledger')) && passed;
  }
  if (routes.runUrl) {
    await navigate(page, routes.runUrl);
    passed = (await ensureVisible(page, '.run-console', 'run activity console')) && passed;
    passed = (await ensureVisible(page, '.search-ledger', 'search provenance ledger')) && passed;
    passed = (await ensureVisible(page, '.run-title-actions', 'run lifecycle controls')) && passed;
  }
  await page.setViewportSize({ width: 375, height: 812 });
  await navigate(page, `${BASE_URL}/app`);
  passed = (await ensureVisible(page, '.mobile-menu', 'mobile navigation control')) && passed;
  const mobileFitsViewport = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth
  );
  if (!mobileFitsViewport) console.error('REHEARSAL FAIL: mobile horizontal overflow');
  else console.log('REHEARSAL OK: mobile viewport has no horizontal overflow');
  passed = mobileFitsViewport && passed;

  await page.evaluate(() => {
    document.documentElement.style.fontSize = '125%';
  });
  const enlargedTextFitsViewport = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth
  );
  if (!enlargedTextFitsViewport) console.error('REHEARSAL FAIL: enlarged text causes horizontal overflow');
  else console.log('REHEARSAL OK: enlarged text preserves the mobile viewport');
  passed = enlargedTextFitsViewport && passed;

  await page.setViewportSize({ width: 844, height: 390 });
  await navigate(page, `${BASE_URL}/app`);
  const landscapeFitsViewport = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth
  );
  if (!landscapeFitsViewport) console.error('REHEARSAL FAIL: landscape horizontal overflow');
  else console.log('REHEARSAL OK: landscape viewport has no horizontal overflow');
  passed = landscapeFitsViewport && passed;

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await navigate(page, `${BASE_URL}/app`);
  const reducedMotionApplied = await page.locator('.evidence-signal__trace').evaluate(
    (element) => Number.parseFloat(getComputedStyle(element).animationDuration) <= 0.01
  );
  if (!reducedMotionApplied) console.error('REHEARSAL FAIL: reduced motion preference');
  else console.log('REHEARSAL OK: reduced motion preference disables signal animation');
  passed = reducedMotionApplied && passed;
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  if (!passed) throw new Error('REHEARSAL FAILED — fix selectors before recording');
  console.log('REHEARSAL PASSED — all selectors verified');
}

async function record(page, routes) {
  await navigate(page, `${BASE_URL}/app`);
  await showSubtitle(page, 'Step 1 — 今日研究任务');
  await page.mouse.move(520, 190, { steps: 10 });
  await page.waitForTimeout(1800);
  await showSubtitle(page, 'Step 2 — 打开最近的研究档案');
  await moveAndClick(page, '.research-ledger__row', 'recent project row', 1800);
  await injectOverlays(page);
  await showSubtitle(page, 'Step 3 — 沿证据链检查当前门禁');
  await page.locator('.research-spine').scrollIntoViewIfNeeded();
  await page.mouse.move(760, 560, { steps: 12 });
  await page.waitForTimeout(2200);
  if (routes.runUrl) {
    await showSubtitle(page, 'Step 4 — 查看检索与运行审计');
    await moveAndClick(page, '.run-list__item', 'latest run entry', 1800);
    await injectOverlays(page);
    await page.locator('.search-ledger').scrollIntoViewIfNeeded();
    await page.waitForTimeout(2600);
  }
  await showSubtitle(page, '证据、决定与产物都留在同一条研究链上');
  await page.waitForTimeout(2400);
  await showSubtitle(page, '');
}

async function exerciseLifecycle(page, routes) {
  if (!routes.projectUrl || !routes.runUrl) {
    throw new Error('Lifecycle mutation QA requires project and run URLs');
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await navigate(page, routes.projectUrl);
  await page.getByRole('button', { name: '编辑项目' }).click();
  const editedName = 'CRUD 生命周期验收（已编辑）';
  await page.getByLabel('项目名称').fill(editedName);
  await page.getByRole('button', { name: '保存修改' }).click();
  await page.getByRole('heading', { name: editedName }).waitFor();

  await page.getByRole('button', { name: '修订方案' }).click();
  await page.getByLabel('起始年份').fill('2020');
  await page.getByLabel(/^本次修订原因/).fill('生命周期 QA：记录试检索后的范围调整');
  await page.getByRole('button', { name: '保存并记录修订' }).click();
  await page.getByText('研究方案已修订').waitFor();
  await page.getByText(/生命周期 QA：记录试检索后的范围调整/).waitFor();

  await navigate(page, `${routes.projectUrl}/documents`);
  const documentRow = page.locator('.document-row-shell').first();
  const filename = (await documentRow.locator('strong').textContent())?.trim() || '';
  await documentRow.getByRole('button', { name: /^删除全文 / }).click();
  await page.locator('.modal input').fill(filename);
  await page.getByRole('button', { name: '确认删除' }).click();
  await documentRow.waitFor({ state: 'detached' });

  await navigate(page, `${routes.projectUrl}/chat`);
  const thread = page.locator('.chat-thread-row').first();
  const threadTitle = (await thread.locator('strong').textContent())?.trim() || '';
  await thread.getByRole('button', { name: /^删除对话 / }).click();
  await page.locator('.modal input').fill(threadTitle);
  await page.getByRole('button', { name: '确认删除' }).click();
  await thread.waitFor({ state: 'detached' });

  await navigate(page, routes.runUrl);
  await page.getByRole('button', { name: '删除运行' }).click();
  await page.locator('.modal input').fill(routes.runUrl.split('/').pop());
  await page.getByRole('button', { name: '确认删除' }).click();
  await page.waitForURL(routes.projectUrl);

  await page.getByRole('button', { name: '编辑项目' }).click();
  await page.getByRole('button', { name: '删除项目' }).click();
  await page.locator('.modal input').fill(editedName);
  await page.getByRole('button', { name: '永久删除' }).click();
  await page.waitForURL(`${BASE_URL}/app/projects`);
  if (await page.getByText(editedName, { exact: true }).isVisible().catch(() => false)) {
    throw new Error('Deleted project is still visible after lifecycle QA');
  }
  console.log('LIFECYCLE QA PASSED — edit and granular deletion workflow verified');
}

(async () => {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.QA_BROWSER_CHANNEL || 'msedge',
    headless: true
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ...(MODE === 'record'
      ? { recordVideo: { dir: OUTPUT_DIR, size: { width: 1440, height: 900 } } }
      : {})
  });
  const page = await context.newPage();
  const browserErrors = [];
  page.on('pageerror', (error) => browserErrors.push(`page: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const location = message.location();
      browserErrors.push(
        `console: ${message.text()}${location.url ? ` (${location.url}:${location.lineNumber})` : ''}`
      );
    }
  });
  page.on('response', (response) => {
    if (response.status() >= 400) {
      browserErrors.push(`response: HTTP ${response.status()} ${response.url()}`);
    }
  });
  const video = page.video();
  try {
    const routes = await projectRoutes();
    if (MODE === 'explore') await explore(page, routes);
    if (MODE === 'rehearse') await rehearse(page, routes);
    if (MODE === 'record') await record(page, routes);
    if (process.env.QA_LIFECYCLE_MUTATE === '1') {
      await exerciseLifecycle(page, routes);
    }
    if (browserErrors.length) {
      throw new Error(`Browser errors detected:\n${browserErrors.join('\n')}`);
    }
  } finally {
    await context.close();
    if (video) {
      const source = await video.path();
      const destination = path.join(OUTPUT_DIR, 'asteria-workflow-demo.webm');
      fs.copyFileSync(source, destination);
      console.log(`Video saved: ${destination}`);
    }
    await browser.close();
  }
})().catch((error) => {
  console.error(`UI DEMO ERROR: ${error.stack || error.message}`);
  process.exit(1);
});
