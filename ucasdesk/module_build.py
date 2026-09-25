"""Shared module transforms for source setup and portable installation."""
from pathlib import Path

def prepare_mooc(root, repo):
    # Extract only the supported functions; upstream's example login URL and
    # hard-coded browser/account settings never enter the generated adapter.
    original = (repo / 'main.mjs').read_text(encoding='utf-8')
    start = original.index('async function deal_video(')
    end = original.index('(async () => {', start)
    code = original[start:end]
    replacements = {
        'console.log(chalk.yellowBright("       Video wait timed out, continuing."));':
            'throw new Error("视频等待超时，学校尚未确认任务点完成。");',
        'console.log(chalk.yellowBright("       " + JSON.stringify(data)));':
            'throw new Error("文档任务点未得到服务器确认。");',
    }
    for old, new in replacements.items():
        if code.count(old) != 1:
            raise RuntimeError('慕课函数结构变化，拒绝生成未经验证的适配器。')
        code = code.replace(old, new)
    header = ('// Generated from wendychan03/ucas-mooc-helper (package metadata: ISC).\n'
              '// Original work: kejaly/ucas_english_mooc. See THIRD_PARTY.md.\n'
              'import chalk from "../vendor/mooc-english/node_modules/chalk/source/index.js";\n')
    (root / 'adapters/mooc_helpers.mjs').write_text(
        header + code + '\nexport { deal_video, deal_pdf };\n', encoding='utf-8')


def prepare_science_lecture(repo):
    """Add the local science-lecture selection policy after upstream patches."""
    files = {
        'src/types.ts': [
            ('  humanityLectureUrl: string;\n', '  humanityLectureUrl: string;\n  scienceMode?: boolean;\n  scienceKeywords?: string[];\n  onePerStartTime?: boolean;\n'),
        ],
        'src/config.ts': [
            ('const fileSchema = z.object({\n', 'const fileSchema = z.object({\n  scienceMode: z.boolean().optional(),\n  onePerStartTime: z.boolean().optional(),\n  scienceKeywords: z.array(z.string()).optional(),\n'),
            ('    humanityLectureUrl: parsedFile.targets?.lectureUrl ?? defaultLectureUrl,\n', '    humanityLectureUrl: parsedFile.targets?.lectureUrl ?? defaultLectureUrl,\n    scienceMode: parsedFile.scienceMode ?? false,\n    onePerStartTime: parsedFile.onePerStartTime ?? false,\n    scienceKeywords: parsedFile.scienceKeywords ?? [],\n'),
        ],
        'src/workflow.ts': [
            ('import { registerLecture } from "./register.js";\n', 'import { registerLecture } from "./register.js";\nimport { parseLectureStart } from "./time-window.js";\n'),
            ('    const decisions = decideLectures(\n      snapshot.lectures.filter(lecture => isYanqiLocation(lecture.location)),\n', '    let eligibleLectures = snapshot.lectures.filter(lecture => isYanqiLocation(lecture.location));\n    if (config.scienceMode && config.onePerStartTime) {\n      const groups = new Map<string, typeof eligibleLectures>();\n      for (const lecture of eligibleLectures) {\n        const parsed = lecture.startTimeText ? parseLectureStart(lecture.startTimeText) : null;\n        const key = parsed ? parsed.date.toISOString().slice(0, 16) : lecture.id;\n        const group = groups.get(key) ?? []; group.push(lecture); groups.set(key, group);\n      }\n      const keywords = (config.scienceKeywords ?? []).map(x => x.toLowerCase());\n      eligibleLectures = [...groups.values()].map(group => group.sort((a, b) => {\n        const score = (x: typeof a) => keywords.reduce((n, k) => n + (x.title.toLowerCase().includes(k) ? 1 : 0), 0);\n        return score(b) - score(a);\n      })[0]);\n    }\n    const decisions = decideLectures(\n      eligibleLectures,\n'),
        ],
    }
    for relative, replacements in files.items():
        path = repo / relative
        text = path.read_text(encoding='utf-8')
        for old, new in replacements:
            if new in text:
                continue
            # The import may already have been added by an older partial
            # installation while the science selection block is still absent.
            # Avoid inserting it twice on the next repair run.
            if relative == 'src/workflow.ts' and old == 'import { registerLecture } from "./register.js";\n' and 'import { parseLectureStart } from "./time-window.js";' in text:
                continue
            if relative == 'src/config.ts' and old.startswith('const fileSchema') and 'scienceMode: z.boolean().optional()' in text:
                continue
            if relative == 'src/workflow.ts' and old.startswith('    const decisions') and 'if (config.scienceMode && config.onePerStartTime)' in text:
                continue
            if old not in text:
                raise RuntimeError(f'科研讲座适配点不存在，拒绝修改 {relative}')
            text = text.replace(old, new, 1)
        path.write_text(text, encoding='utf-8')


