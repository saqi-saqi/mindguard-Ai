/**
 * MindGuard end-to-end + frontend behaviour (Playwright).
 *
 * Selectors are role/label/text based (not CSS classes) so they survive UI refactors.
 * If a label differs in your UI, adjust the regexes in the SELECTORS block only.
 *
 * Run (stack must be up: `docker-compose up -d` or flask + `npm run dev`):
 *   npm i -D @playwright/test @axe-core/playwright && npx playwright install
 *   BASE_URL=http://localhost:5173 npx playwright test e2e/mindguard.spec.ts
 */
import { test, expect, Page } from '@playwright/test';

const BASE = process.env.BASE_URL || 'http://localhost:5173';
const PW = 'Zq!9-E2E-Suite-Pw-7788';

// ---------------------------------------------------------------- SELECTORS
const S = {
  email: /e-?mail|username|user name/i,
  password: /^password$|password/i,
  signUpToggle: /sign ?up|register|create account/i,
  submitSignUp: /sign ?up|register|create account/i,
  submitLogin: /log ?in|sign ?in/i,
  chatInput: /message|type|say|talk|how are you feeling/i,
  send: /send|submit/i,
  logout: /log ?out|sign ?out/i,
};

const uniq = () => `e2e_${Date.now()}_${Math.floor(Math.random() * 1e4)}`;

async function register(page: Page) {
  const id = uniq();
  await page.goto(BASE);
  const toggle = page.getByRole('button', { name: S.signUpToggle }).or(page.getByRole('link', { name: S.signUpToggle }));
  if (await toggle.first().isVisible().catch(() => false)) await toggle.first().click();
  const user = page.getByLabel('Username', { exact: false });
  if (await user.first().isVisible().catch(() => false)) await user.first().fill(id);
  const email = page.getByLabel(/e-?mail/i);
  if (await email.first().isVisible().catch(() => false)) await email.first().fill(`${id}@example.com`);
  await page.getByLabel(S.password).first().fill(PW);
  await page.getByRole('button', { name: S.submitSignUp }).last().click();
  return id;
}

async function openChat(page: Page) {
  await register(page);
  const input = page.getByRole('textbox', { name: S.chatInput }).or(page.getByPlaceholder(S.chatInput)).first();
  await expect(input, 'chat box should be visible after sign up/login').toBeVisible({ timeout: 15_000 });
  return input;
}

async function say(page: Page, text: string) {
  const input = page.getByRole('textbox', { name: S.chatInput }).or(page.getByPlaceholder(S.chatInput)).first();
  await input.fill(text);
  await page.getByRole('button', { name: S.send }).first().click();
}

// ---------------------------------------------------------------- AUTH FLOWS
test.describe('auth', () => {
  test('unauthenticated visitor sees the auth screen, not the chat', async ({ page }) => {
    await page.goto(BASE);
    await expect(page.getByLabel(S.password).first()).toBeVisible();
  });

  test('wrong password shows an error and does not enter the app', async ({ page }) => {
    await page.goto(BASE);
    const email = page.getByLabel(S.email).first();
    await email.fill('nobody@example.com');
    await page.getByLabel(S.password).first().fill('Wrong-Pw-123!');
    await page.getByRole('button', { name: S.submitLogin }).first().click();
    await expect(page.getByRole('alert').or(page.getByText(/invalid|incorrect|wrong|failed|error/i)).first()).toBeVisible();
    await expect(page.getByRole('button', { name: S.send })).toHaveCount(0);
  });

  test('sign up -> chat visible -> reload keeps session -> logout returns to auth', async ({ page }) => {
    await openChat(page);
    await page.reload();
    await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: S.logout }).first().click();
    await expect(page.getByLabel(S.password).first()).toBeVisible();
    // token must be gone from storage
    const leftovers = await page.evaluate(() =>
      Object.entries({ ...localStorage, ...sessionStorage }).filter(([k, v]) => /token|jwt/i.test(k) && v));
    expect(leftovers, 'auth token still in storage after logout').toHaveLength(0);
  });

  test('expired/garbage token sends user back to login instead of a broken UI', async ({ page }) => {
    await page.goto(BASE);
    await page.evaluate(() => {
      for (const k of ['token', 'access_token', 'jwt', 'authToken', 'mindguard_token']) localStorage.setItem(k, 'a.b.c');
    });
    await page.reload();
    await expect(page.getByLabel(S.password).first()).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------- CRISIS UI
test.describe('crisis flow', () => {
  const CRISIS = [
    'I want to kill myself',
    'main khudkushi karna chahta hun',
    'میں خودکشی کرنا چاہتا ہوں',
    'I will kill him and then I will kill myself',
    'I am going to kill my boss tomorrow',
  ];
  for (const text of CRISIS) {
    test(`crisis message shows emergency resources: ${text.slice(0, 30)}`, async ({ page }) => {
      await openChat(page);
      await say(page, text);
      const modal = page.getByRole('dialog').or(page.getByText(/1122/));
      await expect(modal.first(), 'crisis UI (dialog or 1122) must appear').toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(/1122/).first()).toBeVisible();
      await expect(page.getByText(/\b(988|911)\b/)).toHaveCount(0); // no US hotlines for Pakistan users
    });
  }

  test('crisis modal is keyboard accessible and closable with Escape (if it is a dialog)', async ({ page }) => {
    await openChat(page);
    await say(page, 'I want to end my life');
    const dialog = page.getByRole('dialog').first();
    if (!(await dialog.isVisible({ timeout: 10_000 }).catch(() => false))) test.skip(true, 'crisis UI is not a dialog');
    await page.keyboard.press('Tab');
    const focusInside = await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'));
    expect(focusInside, 'focus should be trapped inside the crisis dialog').toBeTruthy();
    await expect(dialog).toHaveAttribute('aria-modal', /true/i);
  });

  test('app keeps working after a crisis message', async ({ page }) => {
    await openChat(page);
    await say(page, 'I want to end my life');
    await page.keyboard.press('Escape');
    await say(page, 'thank you, can you suggest a breathing exercise?');
    await expect(page.getByText(/breath/i).first()).toBeVisible({ timeout: 20_000 });
  });

  test('normal distress does NOT pop the crisis dialog', async ({ page }) => {
    await openChat(page);
    await say(page, 'I feel a bit stressed about my exams');
    await page.waitForTimeout(3000);
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});

// ---------------------------------------------------------------- CHAT ROBUSTNESS
test.describe('chat robustness', () => {
  test('XSS payloads are rendered as text, never executed', async ({ page }) => {
    await openChat(page);
    const dialogs: string[] = [];
    page.on('dialog', (d) => { dialogs.push(d.message()); d.dismiss(); });
    await say(page, '<img src=x onerror="window.__xss=1;alert(1)">');
    await say(page, '<script>window.__xss=2</script>');
    await page.waitForTimeout(2500);
    expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
    expect(dialogs).toHaveLength(0);
  });

  test('very long message does not freeze or crash the UI', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await openChat(page);
    await say(page, 'I feel tired. '.repeat(3000));
    await page.waitForTimeout(3000);
    expect(errors).toEqual([]);
    await expect(page.getByRole('textbox').first()).toBeEnabled();
  });

  test('rapid double-send does not produce duplicate crashes', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await openChat(page);
    const input = page.getByRole('textbox').first();
    await input.fill('hello there');
    const send = page.getByRole('button', { name: S.send }).first();
    await Promise.all([send.click(), send.click({ force: true }).catch(() => {})]);
    await page.waitForTimeout(2000);
    expect(errors).toEqual([]);
  });

  test('empty / whitespace message cannot be sent', async ({ page }) => {
    await openChat(page);
    const before = await page.locator('body').innerText();
    await say(page, '   ');
    await page.waitForTimeout(800);
    expect((await page.locator('body').innerText()).length).toBeLessThan(before.length + 40);
  });

  test('backend down: UI shows an error state instead of crashing', async ({ page, context }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await openChat(page);
    await context.route('**/api/**', (r) => r.abort('connectionrefused'));
    await say(page, 'hello, anyone there?');
    await expect(page.getByText(/error|try again|unable|failed|offline|unavailable|went wrong/i).first()).toBeVisible({ timeout: 15_000 });
    expect(errors).toEqual([]);
  });

  test('backend returns 500: UI recovers and input stays usable', async ({ page, context }) => {
    await openChat(page);
    await context.route('**/api/**chat**', (r) => r.fulfill({ status: 500, body: '{"error":"boom"}', contentType: 'application/json' }));
    await say(page, 'hello');
    await expect(page.getByText(/error|try again|failed|went wrong/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('textbox').first()).toBeEnabled();
  });

  test('slow backend shows a loading indicator', async ({ page, context }) => {
    await openChat(page);
    await context.route('**/api/**chat**', async (r) => { await new Promise((s) => setTimeout(s, 3000)); r.continue(); });
    await say(page, 'tell me something calming');
    await expect(page.getByRole('status').or(page.getByText(/typing|thinking|loading|\.\.\./i)).first()).toBeVisible({ timeout: 2500 });
  });

  test('Urdu / RTL text renders and is sent correctly', async ({ page }) => {
    await openChat(page);
    await say(page, 'آج میں بہت تھکا ہوا ہوں');
    await expect(page.getByText('آج میں بہت تھکا ہوا ہوں').first()).toBeVisible();
  });
});

// ---------------------------------------------------------------- RESPONSIVE + A11Y
test.describe('responsive + accessibility', () => {
  for (const vp of [{ w: 375, h: 667, n: 'mobile' }, { w: 768, h: 1024, n: 'tablet' }, { w: 1440, h: 900, n: 'desktop' }]) {
    test(`no horizontal scroll and chat usable on ${vp.n}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await openChat(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      expect(overflow, 'page scrolls horizontally').toBeFalsy();
      await say(page, 'hello');
      await expect(page.getByRole('textbox').first()).toBeVisible();
    });
  }

  test('auth screen has no serious axe violations', async ({ page }) => {
    let AxeBuilder: any;
    try { AxeBuilder = (await import('@axe-core/playwright')).default; } catch { test.skip(true, 'install @axe-core/playwright'); }
    await page.goto(BASE);
    const res = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    const bad = res.violations.filter((v: any) => ['serious', 'critical'].includes(v.impact));
    expect(bad.map((v: any) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  test('chat screen has no serious axe violations', async ({ page }) => {
    let AxeBuilder: any;
    try { AxeBuilder = (await import('@axe-core/playwright')).default; } catch { test.skip(true, 'install @axe-core/playwright'); }
    await openChat(page);
    const res = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    const bad = res.violations.filter((v: any) => ['serious', 'critical'].includes(v.impact));
    expect(bad.map((v: any) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  test('chat is fully operable by keyboard only', async ({ page }) => {
    await openChat(page);
    await page.getByRole('textbox').first().focus();
    await page.keyboard.type('hello from keyboard');
    await page.keyboard.press('Enter');
    await expect(page.getByText('hello from keyboard').first()).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------- SECURITY (browser side)
test.describe('browser security', () => {
  test('no secrets (API keys / password) in page source or storage', async ({ page }) => {
    await openChat(page);
    const html = await page.content();
    expect(html).not.toMatch(/AIza[0-9A-Za-z_\-]{35}/);
    expect(html).not.toContain(PW);
    const storage = JSON.stringify(await page.evaluate(() => ({ ...localStorage, ...sessionStorage })));
    expect(storage).not.toContain(PW);
    expect(storage).not.toMatch(/AIza[0-9A-Za-z_\-]{35}/);
  });

  test('crisis text is never sent to a third-party host from the browser', async ({ page }) => {
    const hosts = new Set<string>();
    page.on('request', (r) => hosts.add(new URL(r.url()).host));
    await openChat(page);
    hosts.clear();
    await say(page, 'I want to kill myself');
    await page.waitForTimeout(3000);
    const external = [...hosts].filter((h) => !/localhost|127\.0\.0\.1/.test(h) && !h.includes(new URL(BASE).host));
    expect(external, `crisis input triggered requests to: ${external.join(', ')}`).toEqual([]);
  });
});
