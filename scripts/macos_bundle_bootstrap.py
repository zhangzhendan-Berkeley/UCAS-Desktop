"""Run the signed, read-only bundle using a private writable per-build workspace."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def prepare(payload, support):
    manifest = json.loads((payload / 'macos-build.json').read_text())
    build = manifest['build']
    if not build or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in build):
        raise ValueError('Invalid build identifier')
    releases = support / 'releases'
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / build
    with (support / 'bootstrap.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name in ('data', 'logs'):
            (support / name).mkdir(exist_ok=True)
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix='.stage-', dir=releases) as temp:
                stage = Path(temp) / 'app'
                shutil.copytree(payload, stage, symlinks=True)
                for name in ('data', 'logs'):
                    (stage / name).symlink_to(support / name, target_is_directory=True)
                stage.rename(target)
    return target


def main():
    resources = Path(__file__).resolve().parent
    # The override is only for isolated CI/diagnostics; normal Finder launches use this stable location.
    support = Path(os.environ.get('UCAS_MAC_SUPPORT', str(Path.home() / 'Library/Application Support/UCAS Desktop'))).resolve()
    target = prepare(resources / 'payload', support)
    python = target / 'runtime/python/bin/python3'
    env = dict(os.environ, UCAS_NODE=str(target / 'runtime/node/bin/node'), PYTHONNOUSERSITE='1', PYTHONUTF8='1')
    env['PATH'] = str(target / 'runtime/node/bin') + os.pathsep + env.get('PATH', '/usr/bin:/bin')
    for key in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(key, None)
    os.chdir(target)
    os.execve(python, [str(python), str(target / 'app.py'), *sys.argv[1:]], env)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        log = Path.home() / 'Library/Logs/UCAS Desktop'
        log.mkdir(parents=True, exist_ok=True)
        (log / 'launcher-error.log').write_text(traceback.format_exc())
        subprocess.run(['/usr/bin/osascript', '-e', 'display alert "UCAS Desktop 启动失败" message "详情见 ~/Library/Logs/UCAS Desktop/launcher-error.log"'], check=False)
        raise
