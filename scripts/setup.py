"""Reproducible Windows/macOS source setup; no accounts or school operations involved."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=ROOT, capture=False):
    args = [str(x) for x in args]
    if not capture:
        print('>', subprocess.list2cmdline(args), flush=True)
    result = subprocess.run(args, cwd=cwd, check=True, text=True, encoding='utf-8',
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1', 'GIT_TERMINAL_PROMPT': '0'})
    return (result.stdout or '').strip()


def tool(name):
    value = shutil.which(name)
    if not value:
        raise RuntimeError(f'未找到 {name}，请按 README 安装并重新打开终端。')
    return value


def checkout(module):
    target = (ROOT / module['path']).resolve()
    if not target.is_relative_to((ROOT / 'vendor').resolve()):
        raise RuntimeError('模块路径必须在 vendor 中。')
    sha = module['commit']
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise RuntimeError('模块清单含非法 SHA。')
    source = module['source']
    if not source.startswith('https://github.com/'):
        raise RuntimeError('仅支持清单中的 GitHub HTTPS 来源。')
    target.mkdir(parents=True, exist_ok=True)
    if not (target / '.git').exists():
        if any(target.iterdir()):
            raise RuntimeError(f'{target.name} 已有非 Git 内容，请先自行备份。')
        run(['git', 'init', str(target)])
        run(['git', 'remote', 'add', 'origin', source], target)
    origin = run(['git', 'remote', 'get-url', 'origin'], target, True)
    if origin.removesuffix('.git').casefold() != source.removesuffix('.git').casefold():
        raise RuntimeError(f'{target.name} 来源不匹配，不覆盖现有目录。')
    try:
        existing = run(['git', 'rev-parse', '--verify', 'HEAD'], target, True)
    except subprocess.CalledProcessError:
        existing = None
    if existing and existing != sha:
        raise RuntimeError(f'{target.name} 不是固定版本，请备份后移走此目录再安装。')
    if not existing:
        run(['git', 'fetch', '--depth', '1', 'origin', sha], target)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], target)
    if run(['git', 'rev-parse', 'HEAD'], target, True) != sha:
        raise RuntimeError('下载版本校验失败。')
    return target


def prepare_mooc(repo):
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
    (ROOT / 'adapters/mooc_helpers.mjs').write_text(
        header + code + '\nexport { deal_video, deal_pdf };\n', encoding='utf-8')


def prepare_lecture(repo):
    patches = [ROOT / 'patches' / name for name in
               ('lecture-local.patch', 'lecture-sep-workbench.patch', 'lecture-table.patch', 'lecture-campus.patch', 'lecture-browser.patch')]
    first_missing = 0
    for index in reversed(range(len(patches))):
        reverse = subprocess.run(['git', 'apply', '--ignore-space-change', '--reverse', '--check', str(patches[index])],
                                 cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if reverse.returncode == 0:
            first_missing = index + 1
            break
    for patch in patches[first_missing:]:
        run(['git', 'apply', '--ignore-space-change', '--check', str(patch)], repo)
        run(['git', 'apply', '--ignore-space-change', str(patch)], repo)
    for source, destination in [('lecture-register.test.ts', 'tests/register.test.ts'),
                                ('lecture-portal.ts', 'src/portal.ts'),
                                ('lecture-portal.test.ts', 'tests/portal.test.ts'),
                                ('lecture-campus.ts', 'src/campus.ts'),
                                ('lecture-campus.test.ts', 'tests/campus.test.ts')]:
        target = repo / destination
        content = (ROOT / 'patches' / source).read_bytes()
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError(f'{destination} 存在其他修改，不覆盖。')
        target.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-external-modules', action='store_true',
                        help='另行从原仓库获取未附独立 LICENSE 的人文预约与选课依赖；请先阅读 THIRD_PARTY.md')
    parser.add_argument('--check', action='store_true', help='只检查 Python/Git/Node/npm 环境')
    args = parser.parse_args()
    if os.name != 'nt' and sys.platform != 'darwin':
        raise RuntimeError('当前支持 Windows 和 macOS，尚未提供 Linux 账号存储。')
    if sys.version_info[:2] < (3, 10) or sys.version_info[:2] >= (3, 13):
        raise RuntimeError('需要 Python 3.10–3.12。')
    tool('git')
    node = tool('node')
    npm = tool('npm.cmd' if os.name == 'nt' else 'npm')
    version = run([node, '--version'], capture=True)
    if int(version.lstrip('v').split('.')[0]) < 22:
        raise RuntimeError('需要 Node.js 22 或以上；建议 Node.js 24 LTS。')
    print(f'Python {sys.version.split()[0]} / Node {version} / Git / npm: ready', flush=True)
    if args.check:
        return
    python = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    run([python, '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt'])
    for module in json.loads((ROOT / 'modules.json').read_text(encoding='utf-8')):
        if module.get('external_opt_in') and not args.with_external_modules:
            print(f"跳过可选外部模块：{module['name']}", flush=True)
            continue
        repo = checkout(module)
        if module['id'] == 'lecture':
            prepare_lecture(repo)
        if module['id'] in ('mooc', 'lecture'):
            run([npm, 'ci', '--no-audit', '--no-fund'], repo)
        if module['id'] == 'mooc':
            prepare_mooc(repo)
        if module['id'] == 'lecture':
            run([npm, 'run', 'build'], repo)
    if os.name == 'nt':
        run([python, ROOT / 'scripts/build_launcher.py'])
        print('安装完成。双击 UCAS桌面助手.exe 或 启动调试.cmd。学校功能需自行登录验证。')
    else:
        print('安装完成。macOS 请运行：' + str(python) + ' app.py；学校功能需自行登录验证。')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f'安装停止：{exc}', file=sys.stderr)
        sys.exit(1)
