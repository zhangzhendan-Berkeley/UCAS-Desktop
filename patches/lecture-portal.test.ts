import { describe, expect, it } from "vitest";
import { parseScheduleTime, resolvePortalHref, safeLocation } from "../src/portal.js";

describe("SEP portal navigation and privacy", () => {
  it("accepts relative official entry and upgrades SEP SSO to HTTPS", () => {
    expect(resolvePortalHref("/portal/site/524/2412", "https://sep.ucas.ac.cn/sepCard/card"))
      .toBe("https://sep.ucas.ac.cn/portal/site/524/2412");
    expect(resolvePortalHref("http://sep.ucas.ac.cn/portal/site/226/demo", "https://xkgo.ucas.ac.cn:3000/courseManage/main"))
      .toBe("https://sep.ucas.ac.cn/portal/site/226/demo");
  });
  it("rejects fragments, scripts, deceptive hosts and embedded credentials", () => {
    for (const href of ["#", "javascript:alert(1)", "https://sep.ucas.ac.cn.example.com/a", "https://user:secret@sep.ucas.ac.cn/a"]) {
      expect(resolvePortalHref(href, "https://sep.ucas.ac.cn/")).toBeNull();
    }
  });
  it("never logs ticket queries, fragments or encrypted SSO path segments", () => {
    const ticket = "a".repeat(64);
    const safe = safeLocation(`https://sep.ucas.ac.cn/portal/site/226/${ticket}?token=demo#private`);
    expect(safe).toBe("https://sep.ucas.ac.cn/portal/site/226/[REDACTED]");
  });
});

describe("science timetable transfer", () => {
  it("preserves both actual start and end instead of assuming two hours", () => {
    expect(parseScheduleTime("2026-10-16 19:00-20:30")).toEqual({start:"2026-10-16 19:00:00",end:"2026-10-16 20:30:00"});
  });
  it("does not invent dates for invalid or ambiguous times", () => {
    for (const value of ["时间待定", "2026-02-30 19:00-20:30", "2026-09-16 25:00-26:00", "2026-09-16 20:00-19:00"]) {
      expect(parseScheduleTime(value)).toBeNull();
    }
  });
});
