// UCAS Desktop integration helpers. No account-specific portal URLs are stored.
import type { Page } from "playwright";

const allowedHosts = new Set(["sep.ucas.ac.cn", "xkgo.ucas.ac.cn", "xkcts.ucas.ac.cn"]);

export function safeLocation(value: string): string {
  try {
    const url = new URL(value);
    return url.origin + url.pathname.replace(/[a-f0-9]{24,}/gi, "[REDACTED]");
  } catch { return "unknown"; }
}

export function resolvePortalHref(href: string, base: string): string | null {
  try {
    if (!href || href.startsWith("#")) return null;
    const url = new URL(href, base);
    if (!["http:", "https:"].includes(url.protocol) || !allowedHosts.has(url.hostname)
        || url.username || url.password) return null;
    // The new course menu still emits HTTP SEP links; use HTTPS for the SSO hop.
    if (url.hostname === "sep.ucas.ac.cn") url.protocol = "https:";
    return url.href;
  } catch { return null; }
}

export async function findPortalEntry(page: Page): Promise<string | null> {
  const links = await page.locator("a[href]").evaluateAll(anchors => anchors.map(a => ({
    text: (a.textContent ?? "").replace(/\s+/g, " ").trim(),
    href: a.getAttribute("href") ?? ""
  })));
  const candidates = [
    ...links.filter(a => /人文讲座(?:报名|预约)/.test(a.text)),
    ...links.filter(a => /\/subject\/humanity(?:Lecture|Notice)/.test(a.href)),
    ...links.filter(a => a.text === "选课系统")
  ];
  for (const item of candidates) {
    const href = resolvePortalHref(item.href, page.url());
    if (href) return href;
  }
  return null;
}

export async function findLectureBridge(page: Page, kind: "humanity" | "science" = "humanity"): Promise<string | null> {
  const raw = await page.evaluate((type) => {
    const anchors = Array.from(document.querySelectorAll("a[href]"));
    // Both science and humanities use the label 讲座预告. Scope to the right menu.
    const heading = anchors.find(a => a.textContent?.replace(/\s+/g, "").trim() === (type === "science" ? "科学前沿讲座" : "人文讲座"));
    const menu = heading?.closest("li");
    const target = menu && Array.from(menu.querySelectorAll("a[href]")).find(a =>
      /^(讲座预告|人文讲座报名|人文讲座预约)$/.test((a.textContent ?? "").trim()));
    if (target) return target.getAttribute("href");
    return anchors.find(a => (a.getAttribute("href") ?? "").includes(type === "science" ? "/subject/lecture" : "/subject/humanityLecture"))
      ?.getAttribute("href") ?? null;
  }, kind);
  return raw ? resolvePortalHref(raw, page.url()) : null;
}

export async function waitForEntry(find: () => Promise<string | null>, page: Page): Promise<string | null> {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const href = await find();
    if (href) return href;
    await page.waitForTimeout(400);
  }
  return null;
}

export function parseScheduleTime(text: string): { start: string; end: string | null } | null {
  const match = text.match(/(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*[-~～—至]\s*(\d{1,2}:\d{2})/);
  if (!match) return null;
  const [year, month, day] = match[1].split("-").map(Number);
  const format = (value: string) => {
    const [hour, minute] = value.split(":").map(Number);
    const date = new Date(year, month - 1, day, hour, minute);
    if (hour > 23 || minute > 59 || date.getFullYear() !== year || date.getMonth() !== month - 1
        || date.getDate() !== day) return null;
    return `${match[1]} ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00`;
  };
  const start = format(match[2]);
  const end = format(match[3]);
  if (!start || !end || end <= start) return null;
  return { start, end };
}

export async function readScienceSchedule(page: Page) {
  const headings = await page.locator("table th").allTextContents();
  if (!headings.some(x => x.includes("讲座时间")) || !headings.some(x => x.includes("讲座名称"))) {
    throw new Error("讲座时间表结构无法识别；未创建签到任务。");
  }
  const raw = await page.locator("table tr").evaluateAll(rows => rows.map(row =>
    Array.from(row.querySelectorAll("td")).map(td => (td.textContent ?? "").replace(/\s+/g, " ").trim())));
  const index = (name: string) => headings.findIndex(x => x.trim() === name);
  return raw.filter(cells => cells.length >= headings.length).map(cells => {
    const time = cells[index("讲座时间")] ?? "";
    return { title: cells[index("讲座名称")] ?? "", location: cells[index("讲座地点")] ?? "",
      time, ...parseScheduleTime(time) };
  }).filter(row => row.title && row.time);
}
