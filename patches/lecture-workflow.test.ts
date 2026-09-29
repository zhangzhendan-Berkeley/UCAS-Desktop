import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../src/types.js";

const mocks = vi.hoisted(() => ({ register: vi.fn(), mark: vi.fn(), save: vi.fn(), stored: {} as Record<string, any> }));
vi.mock("playwright", () => ({ chromium: { launch: async () => ({
  newContext: async () => ({ newPage: async () => ({ reload: async () => {} }), close: async () => {} }),
  close: async () => {}
}) } }));
vi.mock("../src/login.js", () => ({ ensureAuthenticated: async () => {} }));
vi.mock("../src/register.js", () => ({ registerLecture: mocks.register }));
vi.mock("../src/state-store.js", () => ({
  loadState: async () => ({ terminalLectures: mocks.stored }), saveState: mocks.save,
  markLectureTerminalState: mocks.mark, getStoredLectureState: (state: any, id: string) => state.terminalLectures[id]
}));
vi.mock("../src/lecture-page.js", () => ({ extractLectureSnapshot: async () => ({
  quota: { bookedCount: 1, requiredCount: 10, rawText: "fixture" },
  lectures: [1, 2, 3].map(n => ({ id: String(n), title: `讲座${n}`,
    startTimeText: `2026-10-${20+n} 15:25-17:00`, location: "雁栖湖教一楼",
    terminalState: null, actionAvailable: true }))
}), extractQuotaFromRecordPage: async () => null }));
import { runAutomation } from "../src/workflow.js";

describe("lecture batch policy", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.stored = {}; delete process.env.UCAS_STORAGE_STATE; });
  it('rechecks old full state and registers every currently available lecture', async () => {
    mocks.stored = {'1': {state:'full'}, '3': {state:'booked'}};
    mocks.register.mockImplementation(async (_p, lecture) => ({lectureId:lecture.id,title:lecture.title,outcome:'registered',detail:'ok'}));
    const beforeRegister = vi.fn(async () => {});
    const result = await runAutomation({...config(false), beforeRegister}, logger);
    expect(result.attempts.map(a=>a.lectureId)).toEqual(['1','2']);
    expect(beforeRegister).toHaveBeenCalledTimes(2);
    expect(mocks.save.mock.calls.length).toBeGreaterThanOrEqual(3);
  });
  for (const scienceMode of [false, true]) {
    for (const stopOnUnknown of [undefined, false, true]) {
      it(`continues after clear rejection; science=${scienceMode}, protection=${stopOnUnknown}`, async () => {
        mocks.register.mockImplementation(async (_p, lecture) => ({ lectureId: lecture.id,
          title: lecture.title, outcome: lecture.id === '1' ? 'outside-window' : 'registered', detail: 'fixture' }));
        const result = await runAutomation(config(scienceMode, stopOnUnknown), logger);
        expect(result.attempts.map(x => x.outcome)).toEqual(['outside-window', 'registered', 'registered']);
        expect(mocks.mark.mock.calls.map(x => x[1].id)).toEqual(['2', '3']);
        expect(result.stopReason).toBeNull();
      });
      it(`unknown policy; science=${scienceMode}, protection=${stopOnUnknown}`, async () => {
        mocks.register.mockImplementation(async (_p, lecture) => ({ lectureId: lecture.id,
          title: lecture.title, outcome: lecture.id === '1' ? 'unknown' : 'registered', detail: 'unconfirmed' }));
        const result = await runAutomation(config(scienceMode, stopOnUnknown), logger);
        expect(result.attempts).toHaveLength(stopOnUnknown ? 1 : 3);
        expect(result.attempts[0].outcome).toBe('unknown');
        expect(mocks.mark.mock.calls.some(x => x[1].id === '1')).toBe(false);
        expect(Boolean(result.stopReason)).toBe(Boolean(stopOnUnknown));
      });
    }
  }
});
const logger = { info() {}, debug() {}, error() {} } as any;
function config(scienceMode: boolean, stopOnUnknown?: boolean): AppConfig {
  return { runMode: 'single', dryRun: false, scienceMode, onePerStartTime: true, stopOnUnknown,
    timeWindows: Array.from({length:7}, (_, weekday) => ({weekday,ranges:[{startMinutes:0,endMinutes:1439}]}))
  } as AppConfig;
}
