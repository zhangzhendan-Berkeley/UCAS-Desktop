import { describe, expect, it } from "vitest";
import { classifyRegistrationFeedback } from "../src/register.js";

describe("registration result is conservative", () => {
  it("does not call a failed or ambiguous response successful", () => {
    for (const text of ["报名未成功", "预约失败", "报名成功页面异常", "报名", "操作成功"]) {
      expect(classifyRegistrationFeedback(text)).toBe("unknown");
    }
  });
  it("recognizes explicit target states", () => {
    expect(classifyRegistrationFeedback("已预约 取消预约")).toBe("registered");
    expect(classifyRegistrationFeedback("报名成功")).toBe("registered");
    expect(classifyRegistrationFeedback("名额已满")).toBe("full");
  });
});
