import type { Page, BrowserContext } from "playwright";

export const backgroundArgs = ["--start-minimized", "--disable-background-timer-throttling", "--disable-renderer-backgrounding"];
const watched = new WeakSet<BrowserContext>();
export async function setSepWindow(page: Page, visible: boolean): Promise<void> {
  if (page.isClosed()) return;
  const session = await page.context().newCDPSession(page);
  try {
    const { windowId } = await session.send("Browser.getWindowForTarget");
    await session.send("Browser.setWindowBounds", {windowId, bounds:{windowState:visible ? "normal" : "minimized"}});
    if (visible) await page.bringToFront();
  } finally { await session.detach(); }
}
export async function backgroundSep(page: Page, headless: boolean): Promise<void> {
  if (headless) return;
  const context=page.context();
  if (!watched.has(context)) {
    watched.add(context);
    context.on("page", child => { setSepWindow(child,false).catch(()=>{}); });
  }
  await setSepWindow(page,false);
}
export async function revealSep(page: Page): Promise<void> {
  await setSepWindow(page,true);
}
