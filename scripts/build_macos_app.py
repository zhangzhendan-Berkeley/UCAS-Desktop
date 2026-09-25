#!/usr/bin/env python3
"""Build a lightweight macOS app bundle for the current checkout."""
from pathlib import Path
import plistlib
import shutil
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    output = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else root / 'Ucas Desktop.app'
    if not output.is_absolute():
        output = Path.cwd() / output
    contents = output / 'Contents'
    macos = contents / 'MacOS'
    resources = contents / 'Resources'
    if output.exists():
        shutil.rmtree(output)
    macos.mkdir(parents=True)
    resources.mkdir()
    launcher = macos / 'Ucas Desktop'
    launcher.write_text(
        '#!/bin/sh\nset -eu\n'
        f'cd {str(root)!r}\n'
        'exec ./启动mac.sh "$@"\n', encoding='utf-8'
    )
    launcher.chmod(0o755)
    icon = root / 'assets' / 'app.icns'
    if icon.exists():
        shutil.copy2(icon, resources / icon.name)
    info = {
        'CFBundleDisplayName': 'UCAS Desktop',
        'CFBundleExecutable': 'Ucas Desktop',
        'CFBundleIdentifier': 'com.zhangzhendan.ucas-desktop',
        'CFBundleName': 'UCAS Desktop',
        'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '0.5.2',
        'CFBundleVersion': '0.5.2',
        'LSMinimumSystemVersion': '13.0',
        'NSHighResolutionCapable': True,
    }
    if icon.exists():
        info['CFBundleIconFile'] = 'app.icns'
    with (contents / 'Info.plist').open('wb') as handle:
        plistlib.dump(info, handle)
    print(output)


if __name__ == '__main__':
    main()
