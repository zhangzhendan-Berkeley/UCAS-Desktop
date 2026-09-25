"""Build an architecture-native .app without depending on Homebrew or developer Python."""
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ucasdesk.portable import archive_url, download, unpack_repo, stamp_module
from ucasdesk.module_build import prepare_mooc

VERSION = '0.5.2-mac.1'
PYTHON = '3.12.14'
PBS = '20260924'
NODE = '24.21.0'
HASHES = {
    'arm64': ('aarch64', '9763f43db2481a6af36af82ec40302aab7a73632f880129d07a6e81aec846277', 'bed7eea5325e1108f32ce5228ddd6a5f0f08a499ee42aa7442aea583702f6057'),
    'x64': ('x86_64', '0d6a4a299908123f00bc844df737603f047ff9eba14fda6cad83f3cf3cb3a2af', '1462cb3b3046b815cf8ea436d3da450ec1a9f11dac7e5a46b0ada5305d7e8097'),
}


def run(args, cwd=ROOT, env=None):
    subprocess.run([str(x) for x in args], cwd=cwd, env=env, check=True)


def main():
    if sys.platform != 'darwin':
        raise RuntimeError('Build on native macOS')
    arch = 'arm64' if platform.machine() == 'arm64' else 'x64'
    triple, py_hash, node_hash = HASHES[arch]
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    out = ROOT / 'dist' / f'UCAS-Desktop-{VERSION}-macOS-{arch}'
    out.mkdir(parents=True, exist_ok=False)
    app = out / 'UCAS Desktop.app'
    contents = app / 'Contents'
    resources = contents / 'Resources'
    payload = resources / 'payload'
    payload.mkdir(parents=True)
    # Only tracked source files; never copy developer profiles, generated files or vendor checkouts.
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    roots = {'ucasdesk', 'adapters', 'assets', 'mobile', 'patches', 'scripts', 'tests', 'docs'}
    names = {'app.py', 'requirements.txt', 'modules.json', 'modules-downloads.json', 'LICENSE', 'README.md', 'THIRD_PARTY.md', '使用指南.md'}
    for name in filter(None, tracked):
        if Path(name).parts[0] in roots or name in names:
            dest = payload / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
    cache = ROOT / 'data/mac-build-cache'
    cache.mkdir(parents=True, exist_ok=True)
    runtime = payload / 'runtime'
    runtime.mkdir()
    sources = [
        ('python', f'https://github.com/astral-sh/python-build-standalone/releases/download/{PBS}/cpython-{PYTHON}%2B{PBS}-{triple}-apple-darwin-install_only.tar.gz', py_hash),
        ('node', f'https://nodejs.org/dist/v{NODE}/node-v{NODE}-darwin-{arch}.tar.gz', node_hash),
    ]
    for name, url, digest in sources:
        archive = cache / (name + '-' + arch + '.tar.gz')
        archive.write_bytes(download(url, digest))
        stage = cache / (name + '-' + arch)
        stage.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(stage, filter='data')
        extracted = next(stage.iterdir())
        shutil.move(str(extracted), runtime / name)
    python = runtime / 'python/bin/python3'
    node = runtime / 'node/bin/node'
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1', UCAS_NODE=str(node))
    env['PATH'] = str(node.parent) + os.pathsep + os.environ.get('PATH', '')
    run([python, '-m', 'pip', 'install', '--only-binary=:all:', '--no-compile', '--report', runtime / 'python-dependencies.json', '-r', payload / 'requirements.txt'], env=env)
    modules = json.loads((payload / 'modules.json').read_text())
    checksums = json.loads((payload / 'modules-downloads.json').read_text())
    for module in modules:
        if module['id'] not in ('lecture', 'mooc', 'planner'):
            continue
        source = cache / module['id']
        unpack_repo(download(archive_url(module), checksums[module['id']]['archive_sha256']), source)
        if module['id'] in ('lecture', 'mooc'):
            run([node, runtime / 'node/lib/node_modules/npm/bin/npm-cli.js', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=source, env=env)
            shutil.copytree(source / 'node_modules', runtime / (module['id'] + '-node/node_modules'), symlinks=True)
        if module['id'] == 'mooc':
            target = payload / module['path']
            target.mkdir(parents=True)
            for name in ('package.json', 'package-lock.json'):
                shutil.copy2(source / name, target / name)
            shutil.copytree(source / 'node_modules', target / 'node_modules', symlinks=True)
            prepare_mooc(payload, source)
            (target / 'SOURCE.md').write_text('Source: https://github.com/wendychan03/ucas-mooc-helper\nOriginal: https://github.com/kejaly/ucas_english_mooc\nISC; complete used source: ../../adapters/mooc_helpers.mjs\nSee ../../THIRD_PARTY.md and ../../modules.json.\n')
            stamp_module(payload, module)
        if module['id'] == 'planner':
            target = payload / module['path']
            for directory in ('src', 'data'):
                shutil.copytree(source / directory, target / directory)
            for name in ('LICENSE', 'README.md', 'pyproject.toml'):
                shutil.copy2(source / name, target / name)
            stamp_module(payload, module)
    manifest = {'version': VERSION, 'build': VERSION + '-' + arch + '-' + commit[:12], 'commit': commit, 'arch': arch, 'python': PYTHON, 'node': NODE}
    (payload / 'macos-build.json').write_text(json.dumps(manifest, indent=2))
    # Remove build bytecode, which can contain CI paths; no user state belongs in this bundle.
    for directory in list(payload.rglob('__pycache__')):
        shutil.rmtree(directory)
    assert not (payload / 'data').exists() and not (payload / 'logs').exists()
    for path in payload.rglob('*'):
        if path.is_file() and (path.suffix.lower() in {'.dpapi', '.db', '.sqlite'} or path.name == '.env'):
            raise RuntimeError('Private state in package: ' + str(path))
    shutil.copy2(ROOT / 'scripts/macos_bundle_bootstrap.py', resources / 'bootstrap.py')
    macos = contents / 'MacOS'
    macos.mkdir()
    # Finder launches a real native executable; paths are resolved relative to this bundle.
    source = cache / 'launcher.c'
    source.write_text(r'''
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    char raw[PATH_MAX], path[PATH_MAX], python[PATH_MAX], script[PATH_MAX];
    uint32_t size=sizeof(raw);
    if (_NSGetExecutablePath(raw,&size) || !realpath(raw,path)) return 1;
    char *slash=strrchr(path,'/'); if (!slash) return 1; *slash=0;
    snprintf(python,sizeof(python),"%s/../Resources/payload/runtime/python/bin/python3",path);
    snprintf(script,sizeof(script),"%s/../Resources/bootstrap.py",path);
    char **args=calloc(argc+2,sizeof(char*)); args[0]=python; args[1]=script;
    for(int i=1;i<argc;i++) args[i+1]=argv[i];
    unsetenv("PYTHONHOME"); unsetenv("PYTHONPATH");
    setenv("PYTHONNOUSERSITE","1",1); setenv("PYTHONDONTWRITEBYTECODE","1",1);
    execv(python,args); perror("UCAS Desktop launcher"); return 1;
}
''')
    run(['clang', '-Os', '-mmacosx-version-min=13.0', source, '-o', macos / 'UCAS Desktop'])
    helper = runtime / 'calendar/ucas-calendar'
    helper.parent.mkdir()
    usage = '将你选择的国科大课程和已报名讲座添加到 iCloud 的 UCAS 日历，并更新本应用创建的事件。'
    helper_plist = cache / 'CalendarInfo.plist'
    with helper_plist.open('wb') as f:
        plistlib.dump({'CFBundleIdentifier': 'com.zhangzhendan.ucas-desktop.calendar', 'CFBundleName': 'UCAS Desktop Calendar', 'NSCalendarsUsageDescription': usage, 'NSCalendarsFullAccessUsageDescription': usage}, f)
    run(['swiftc', '-O', '-target', ('arm64' if arch == 'arm64' else 'x86_64') + '-apple-macosx13.0', ROOT / 'scripts/icloud_calendar.swift', '-o', helper,
         '-Xlinker', '-sectcreate', '-Xlinker', '__TEXT', '-Xlinker', '__info_plist', '-Xlinker', helper_plist])
    run([python, '-c', 'from PIL import Image; import sys; Image.open(sys.argv[1]).save(sys.argv[2], format="ICNS")', ROOT / 'assets/app.png', resources / 'app.icns'], env=env)
    with (contents / 'Info.plist').open('wb') as f:
        plistlib.dump({'CFBundleExecutable': 'UCAS Desktop', 'CFBundleIdentifier': 'com.zhangzhendan.ucas-desktop', 'CFBundleName': 'UCAS Desktop', 'CFBundleDisplayName': 'UCAS Desktop', 'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.5.2', 'CFBundleVersion': '0.5.2.1', 'CFBundleIconFile': 'app.icns', 'LSMinimumSystemVersion': '13.0', 'NSHighResolutionCapable': True, 'NSCalendarsUsageDescription': usage, 'NSCalendarsFullAccessUsageDescription': usage}, f)
    # Ad-hoc signing guarantees integrity; it is NOT Apple Developer ID notarization.
    run(['codesign', '--force', '--deep', '--sign', '-', app])
    run(['codesign', '--verify', '--deep', '--strict', '--verbose=2', app])
    shutil.copy2(ROOT / 'docs/macOS便携版说明.md', out / '先读我.md')
    print('Built:', app, flush=True)


if __name__ == '__main__':
    main()
