"""Build a clean Windows x64 portable ZIP with an independent CPython and Node."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ucasdesk.portable import download, archive_url, unpack_repo

PYTHON_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
PYTHON_SHA = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
NODE_URL = 'https://nodejs.org/dist/v24.21.0/node-v24.21.0-win-x64.zip'
NODE_SHA = '158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541'


def run(args, cwd=ROOT, extra=None):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONNOUSERSITE='1')
    env.update(extra or {})
    subprocess.run([str(x) for x in args], cwd=cwd, env=env, check=True)


def cached(cache, name, url, checksum=None):
    path = cache / name
    if not path.is_file() or (checksum and hashlib.sha256(path.read_bytes()).hexdigest() != checksum):
        print('Downloading:', name, flush=True)
        content = download(url, checksum)
        path.write_bytes(content)
    return path.read_bytes()


def ignore(directory, names):
    return [n for n in names if n in ('.git', '__pycache__', '.pytest_cache', '.env', '.venv')
            or (Path(directory).name == 'python' and n == 'Scripts')
            or n.endswith(('.pyc', '.pyo', '.dpapi'))]


def copy_contents(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore)


def trim_qt(output):
    """Keep the replaceable Qt modules/plugins actually used by this Widgets app."""
    qt = (output / 'runtime/python/Lib/site-packages/PySide6').resolve()
    assert qt.is_relative_to(output.resolve())
    modules = {'Core', 'Gui', 'Widgets', 'Network', 'Svg', 'SvgWidgets', 'PrintSupport', 'OpenGL', 'OpenGLWidgets'}
    for path in qt.iterdir():
        if path.is_dir() and path.name in {'qml', 'resources', 'lib', 'include', 'typesystems', 'metatypes', 'glue', 'doc'}:
            assert path.resolve().is_relative_to(qt)
            shutil.rmtree(path)
        elif path.is_file() and (path.suffix == '.exe'
                or (path.name.startswith('Qt6') and path.suffix == '.dll' and path.stem[3:] not in modules)
                or (path.name.startswith('Qt') and path.suffix in {'.pyd', '.pyi'} and path.stem[2:] not in modules)
                or path.name.startswith(('avcodec-', 'avformat-', 'avutil-', 'swresample-', 'swscale-'))):
            path.unlink()
    plugins = qt / 'plugins'
    for path in plugins.iterdir():
        if path.is_dir() and path.name not in {'platforms', 'imageformats', 'styles', 'tls', 'networkinformation', 'iconengines'}:
            assert path.resolve().is_relative_to(qt)
            shutil.rmtree(path)
    (plugins / 'imageformats/qpdf.dll').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.3.2')
    parser.add_argument('--no-zip', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Resume this version only before it has ever been run')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Build on Windows x64')
    cache = ROOT / 'data/portable-cache'
    cache.mkdir(parents=True, exist_ok=True)
    output = ROOT / 'dist' / f'UCAS-Desktop-{args.version}-Windows-x64'
    if output.exists() and (not args.resume or (output / 'data').exists() or (output / 'logs').exists()
                            or not (output / 'runtime/python/python312.dll').is_file()):
        raise RuntimeError('输出目录已存在或已运行，拒绝覆盖：' + str(output))
    # Cache an actual embedded interpreter, never copy a developer venv.
    python_dir = cache / 'python'
    python_dir.mkdir(exist_ok=True)
    if not (python_dir / 'python.exe').is_file():
        with zipfile.ZipFile(io.BytesIO(cached(cache, 'python-3.12.10-embed-amd64.zip', PYTHON_URL, PYTHON_SHA))) as z:
            z.extractall(python_dir)
    (python_dir / 'python312._pth').write_text('python312.zip\n.\nLib\\site-packages\n..\\..\nimport site\n', encoding='utf-8')
    python = python_dir / 'python.exe'
    site = python_dir / 'Lib/site-packages'
    if not (site / 'pip').exists():
        run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '--no-compile', '--target', site, 'pip==25.0.1'])
    digest = hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).hexdigest()
    marker = python_dir / 'requirements.sha256'
    if not marker.is_file() or marker.read_text() != digest:
        print('Installing isolated Python runtime dependencies…', flush=True)
        run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '--no-compile',
             '--only-binary=:all:', '--report', cache / 'python-install-report.json', '-r', ROOT / 'requirements.txt'])
        marker.write_text(digest)
    node_dir = cache / 'node'
    if not (node_dir / 'node.exe').is_file():
        node_dir.mkdir(exist_ok=True)
        unpack_repo(cached(cache, 'node-v24.21.0-win-x64.zip', NODE_URL, NODE_SHA), node_dir)
    node = node_dir / 'node.exe'
    npm = node_dir / 'node_modules/npm/bin/npm-cli.js'
    env = {'PATH': str(node_dir) + os.pathsep + os.environ.get('PATH', ''), 'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD': '1'}
    modules = json.loads((ROOT / 'modules.json').read_text(encoding='utf-8'))
    sources, manifest = {}, {}
    for module in modules:
        if module['id'] == 'iclass':
            continue  # Python implementation and attribution are already in our source.
        content = cached(cache, module['id'] + '-' + module['commit'] + '.zip', archive_url(module))
        manifest[module['id']] = {'commit': module['commit'], 'archive_sha256': hashlib.sha256(content).hexdigest()}
        path = cache / ('source-' + module['id'])
        if not path.is_dir():
            unpack_repo(content, path)
        sources[module['id']] = path
        if module['id'] in ('lecture', 'mooc'):
            if not (path / 'node_modules').is_dir():
                print('Preparing Node dependencies:', module['id'], flush=True)
                run([node, npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], path, env)
    output.mkdir(parents=True, exist_ok=True)
    for directory in ('ucasdesk', 'adapters', 'assets', 'mobile', 'patches', 'scripts', 'build', 'tests', 'docs'):
        copy_contents(ROOT / directory, output / directory)
    # The helper is generated from the pinned public source below, not from local state.
    generated = output / 'adapters/mooc_helpers.mjs'
    if generated.exists():
        generated.unlink()
    for filename in ('app.py', 'requirements.txt', 'modules.json', 'LICENSE', 'README.md', 'THIRD_PARTY.md', '使用指南.md'):
        shutil.copy2(ROOT / filename, output / filename)
    copy_contents(python_dir, output / 'runtime/python')
    # pip console wrappers contain the build interpreter's absolute path and are unused.
    wrappers = (output / 'runtime/python/Scripts').resolve()
    assert wrappers.is_relative_to(output.resolve())
    if wrappers.exists():
        shutil.rmtree(wrappers)
    # Standalone OCR workers do not import Qt first. Put the wheel's redistributable
    # MSVC DLLs beside python.exe so they never depend on a developer's system DLLs.
    for pattern in ('msvcp140*.dll', 'vcruntime140*.dll', 'concrt140.dll'):
        for dll in (output / 'runtime/python/Lib/site-packages/PySide6').glob(pattern):
            shutil.copy2(dll, output / 'runtime/python' / dll.name)
    trim_qt(output)
    copy_contents(node_dir, output / 'runtime/node')
    copy_contents(sources['lecture'] / 'node_modules', output / 'runtime/lecture-node/node_modules')
    # MIT planner source and its upstream course snapshot; no personal planner database.
    copy_contents(sources['planner'] / 'src', output / 'vendor/UCAS-Course-Selector/src')
    planner_data = output / 'vendor/UCAS-Course-Selector/data'
    planner_data.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sources['planner'] / 'data/2026年秋季学期课表.xlsx', planner_data / '2026年秋季学期课表.xlsx')
    for name in ('LICENSE', 'README.md', 'pyproject.toml'):
        shutil.copy2(sources['planner'] / name, output / 'vendor/UCAS-Course-Selector' / name)
    mooc = output / 'vendor/mooc-english'
    mooc.mkdir(parents=True, exist_ok=True)
    # Never redistribute upstream's demo login URL, account settings or screenshots.
    for path in mooc.iterdir():
        if path.name not in {'node_modules', 'package.json', 'package-lock.json', 'SOURCE.md'}:
            assert path.resolve().is_relative_to(mooc.resolve())
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
    for name in ('package.json', 'package-lock.json'):
        shutil.copy2(sources['mooc'] / name, mooc / name)
    copy_contents(sources['mooc'] / 'node_modules', mooc / 'node_modules')
    (mooc / 'SOURCE.md').write_text(
        'Source: https://github.com/wendychan03/ucas-mooc-helper\n'
        'Original work: https://github.com/kejaly/ucas_english_mooc\n'
        'License field: ISC; see package.json and ../../THIRD_PARTY.md.\n'
        'The complete source of the functions used by this app is in ../../adapters/mooc_helpers.mjs.\n'
        'Upstream demo login settings are excluded. Fixed revision: ../../modules.json.\n', encoding='utf-8')
    spec = importlib.util.spec_from_file_location('portable_setup', ROOT / 'scripts/setup.py')
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    setup.ROOT = output
    setup.prepare_mooc(sources['mooc'])
    (output / 'runtime/modules-downloads.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    run([python, output / 'scripts/build_launcher.py'], output)
    report = json.loads((cache / 'python-install-report.json').read_text(encoding='utf-8'))
    dependencies = [{'name': x['metadata']['name'], 'version': x['metadata']['version'],
                     'license': x['metadata'].get('license'), 'download': x['download_info']}
                    for x in report['install']]
    (output / 'runtime/python-dependencies.json').write_text(json.dumps(dependencies, ensure_ascii=False, indent=2), encoding='utf-8')
    licenses = output / 'runtime/licenses/Qt'
    licenses.mkdir(parents=True, exist_ok=True)
    for name in ('LGPL-3.0-only.txt', 'GPL-3.0-only.txt'):
        content = cached(cache, 'Qt-' + name, 'https://raw.githubusercontent.com/pyside/pyside-setup/v6.10.1/LICENSES/' + name)
        (licenses / name).write_bytes(content)
    (licenses / 'SOURCES.txt').write_text(
        'Qt / PySide6 6.10.1; libraries are dynamically loaded and replaceable.\n'
        'PySide6 source: https://github.com/pyside/pyside-setup/tree/v6.10.1\n'
        'Qt source: https://download.qt.io/archive/qt/6.10/6.10.1/single/qt-everywhere-src-6.10.1.tar.xz\n'
        'Licensing: https://doc.qt.io/qtforpython-6/licenses.html\n', encoding='utf-8')
    (output / 'portable-version.json').write_text(json.dumps({'version': args.version, 'python': '3.12.10', 'node': '24.21.0',
        'python_sha256': PYTHON_SHA, 'node_sha256': NODE_SHA, 'source': 'https://github.com/zhangzhendan-Berkeley/UCAS-Desktop'}, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'docs/便携版说明.md', output / '先读我.md')
    (output / '启动诊断.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"runtime\\python\\python.exe" app.py\r\npause\r\n', encoding='ascii')
    # No developer state or local paths belong in a distributable.
    assert not (output / 'data').exists() and not (output / 'logs').exists()
    for path in output.rglob('*'):
        if path.is_file() and (path.suffix.lower() in ('.dpapi', '.db', '.sqlite') or path.name == '.env'):
            raise RuntimeError('Private-state file in package: ' + str(path.relative_to(output)))
    print('Portable directory ready:', output, flush=True)
    if not args.no_zip:
        zip_path = Path(shutil.make_archive(str(output), 'zip', output.parent, output.name))
        checksum = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        zip_path.with_suffix('.zip.sha256').write_text(checksum + '  ' + zip_path.name + '\n')
        print('ZIP:', zip_path, 'bytes:', zip_path.stat().st_size, 'SHA256:', checksum, flush=True)


if __name__ == '__main__':
    main()
