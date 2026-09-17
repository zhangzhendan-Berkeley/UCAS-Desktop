"""Prepare a complete app-code overlay, never a diff against the developer's HEAD."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def prepare(root, output, version):
    if output.exists(): raise ValueError('输出目录已存在，请使用新的目录。')
    paths = []
    for name in ('ucasdesk', 'adapters', 'docs', 'mobile'):
        paths.extend(p for p in (root / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo', '.dpapi'))
    paths.extend(root / name for name in ('README.md', '使用指南.md'))
    manifest = {}
    for path in paths:
        name = path.relative_to(root).as_posix()
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / 'update-manifest.json').write_text(json.dumps({'version': version, 'files': manifest}, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    files = prepare(Path(__file__).resolve().parents[1], args.output.resolve(), args.version)
    print('Prepared complete app-code update:', len(files), 'files')
