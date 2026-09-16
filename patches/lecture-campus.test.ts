import { describe, it, expect } from "vitest";
import { isYanqiLocation } from "../src/campus.js";

describe("Yanqi-only registration", () => {
  it("requires an unambiguous Yanqi Lake venue", () => {
    expect(isYanqiLocation("雁栖湖校区 教一楼 101")).toBe(true);
    expect(isYanqiLocation("雁栖湖国际会议中心")).toBe(true);
    for (const value of [null, "", "教一楼101", "中关村教学楼", "玉泉路礼堂", "雁栖湖/玉泉路", "线上（雁栖湖主办）", "雁栖湖，地点待定"]) {
      expect(isYanqiLocation(value)).toBe(false);
    }
  });
});
