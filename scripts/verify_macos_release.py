"""Exercise the actual relocated bundle, without school accounts or iCloud writes."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    arch = 'arm64' if platform.machine() == 'arm64' else 'x64'
    original = ROOT / f'dist/UCAS-Desktop-0.5.2-mac.1-macOS-{arch}/UCAS Desktop.app'
    area = ROOT / 'data/mac-verify'
    area.mkdir(parents=True)
    relocated = area / 'Moved folder with spaces/UCAS Desktop.app'
    relocated.parent.mkdir()
    shutil.copytree(original, relocated, symlinks=True)
    support = area / 'Application Support'
    # Finder has a minimal PATH; nothing may require Homebrew, Python, npm, or Swift.
    env = dict(os.environ, UCAS_MAC_SUPPORT=str(support), PATH='/usr/bin:/bin:/usr/sbin:/sbin', PYTHONNOUSERSITE='1')
    env.pop('QT_QPA_PLATFORM', None)
    subprocess.run([str(relocated / 'Contents/MacOS/UCAS Desktop'), '--smoke-test'], env=env, check=True, timeout=180)
    target = next((support / 'releases').iterdir())
    report = json.loads((target / 'logs/launcher-smoke.json').read_text())
    assert report['planner_loaded']
    assert Path(report['python']).is_relative_to(target)
    python = target / 'runtime/python/bin/python3'
    node = target / 'runtime/node/bin/node'
    env.update(UCAS_NODE=str(node), QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
    def run(args, **kwargs):
        subprocess.run([str(x) for x in args], cwd=target, env=env, check=True, timeout=300, **kwargs)
    run([python, 'scripts/check_install.py'])
    run([python, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    run([python, 'scripts/keychain_self_test.py'])
    run([python, 'tests/macos_jobs_smoke.py'])
    run([node, 'tests/mooc_course_smoke.mjs'])
    helper = target / 'runtime/calendar/ucas-calendar'
    run([helper, '--self-test'], input='[{"start":100,"end":200,"title":"课程 · 中文","location":"教一楼"}]', text=True)
    run([python, '-c', "import json; from pathlib import Path; from ucasdesk.portable import install_module; r=Path.cwd(); mods=json.loads((r/'modules.json').read_text()); [install_module(r,m) for m in mods if m['id'] in ('lecture','selection')]"])
    run([python, 'scripts/check_install.py'])
    run([node, 'tests/lecture_portal_smoke.mjs'])
    run([node, 'tests/lecture_captcha_smoke.mjs'])
    (target / 'adapters/mooc_helpers.mjs').unlink()
    (target / 'vendor/ucas-humanity-lecture-bot/dist/src/background.js').unlink()
    run([python, '-c', "import json; from pathlib import Path; from ucasdesk.portable import install_module,ready; r=Path.cwd(); mods=json.loads((r/'modules.json').read_text()); broken=[m for m in mods if m['id'] in ('lecture','mooc')]; assert all(not ready(r,m) for m in broken); [install_module(r,m) for m in broken]; assert all(ready(r,m) for m in broken)"])
    # Re-launch reuses the workspace and private state rather than replacing it.
    sentinel = support / 'data/preservation-test.txt'
    sentinel.write_text('keep me')
    subprocess.run([str(relocated / 'Contents/MacOS/UCAS Desktop'), '--smoke-test'], env=env, check=True, timeout=60)
    assert sentinel.read_text() == 'keep me'
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(original)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(relocated)], check=True)
    payload = original / 'Contents/Resources/payload'
    assert not (payload / 'data').exists() and not (payload / 'logs').exists()
    result = {'architecture': arch, 'system': platform.mac_ver()[0], 'native_app_launch': True, 'bundled_runtime': True, 'planner': True, 'keychain': True, 'mooc_dom': True, 'component_install_repair': True, 'calendar_helper': True, 'private_state_preserved': True, 'real_icloud_sync': 'not tested; no private account in CI'}
    (ROOT / f'dist/verification-{arch}.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
