"""Apply a prepared, hashed source overlay only while the target app is stopped."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys


def apply(source, target):
    from PySide6.QtCore import QLockFile
    source, target = source.resolve(), target.resolve()
    if source == target or not (target / 'app.py').is_file() or not (target / 'data').is_dir():
        raise ValueError('目标必须是已有的 UCAS 桌面助手目录。')
    manifest = json.loads((source / 'update-manifest.json').read_text(encoding='utf-8'))
    files = []
    for name, expected in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in ('ucasdesk', 'adapters', 'docs', 'mobile', 'README.md', '使用指南.md'):
            raise ValueError('更新清单含不允许的路径。')
        incoming, destination = (source / relative).resolve(), (target / relative).resolve()
        if not incoming.is_relative_to(source) or not destination.is_relative_to(target):
            raise ValueError('更新路径超出应用目录。')
        if hashlib.sha256(incoming.read_bytes()).hexdigest() != expected:
            raise ValueError('更新文件校验失败：' + name)
        files.append((relative, incoming, destination))
    lock = QLockFile(str(target / 'data/app.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        raise RuntimeError('App 仍在运行。请等慕课任务结束后，右键托盘选择“退出程序”，再运行此升级入口。没有修改任何程序文件。')
    backup = target / 'data' / 'update-backups' / datetime.now().strftime('%Y%m%d-%H%M%S')
    changed = []
    try:
        for relative, incoming, destination in files:
            if destination.exists():
                copy = backup / relative
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, copy)
            changed.append((relative, destination, destination.exists()))
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + '.update')
            shutil.copy2(incoming, temporary)
            temporary.replace(destination)
        print('升级完成：' + manifest['version'])
        print('账号、任务、课表和慕课登录状态已保留。旧程序文件备份：' + str(backup))
    except Exception:
        for relative, destination, existed in reversed(changed):
            if existed: shutil.copy2(backup / relative, destination)
            elif destination.exists(): destination.unlink()
        raise
    finally:
        lock.unlock()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    try: apply(args.source, args.target)
    except Exception as exc:
        print('未完成升级：' + str(exc))
        sys.exit(1)
