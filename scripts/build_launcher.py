"""Build the small Windows launcher and, optionally, a desktop shortcut."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--shortcut', action='store_true', help='创建桌面快捷方式')
args = parser.parse_args()
subprocess.run([sys.executable, str(ROOT / 'build/make_icon.py')], cwd=ROOT, check=True)
windows = Path(os.environ.get('WINDIR', 'C:/Windows'))
compilers = [windows / 'Microsoft.NET' / folder / 'v4.0.30319/csc.exe'
             for folder in ('Framework64', 'Framework')]
compiler = next((p for p in compilers if p.exists()), None)
if not compiler:
    raise SystemExit('未找到 .NET Framework csc.exe。仍可使用 启动调试.cmd 启动。')
subprocess.run([str(compiler), '/nologo', '/target:winexe', '/reference:System.Windows.Forms.dll',
                '/win32icon:assets\\app.ico', '/out:UCAS桌面助手.exe', '.\\build\\Launcher.cs'],
               cwd=ROOT, check=True)
if args.shortcut:
    # Paths are read from the current directory rather than interpolated into shell code.
    command = """$rootDir = (Get-Location).Path
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'UCAS桌面助手.lnk'))
$link.TargetPath = Join-Path $rootDir 'UCAS桌面助手.exe'
$link.WorkingDirectory = $rootDir
$link.IconLocation = (Join-Path $rootDir 'assets\\app.ico') + ',0'
$link.Description = 'UCAS 桌面助手 · 托盘后台运行'
$link.Save()
"""
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], cwd=ROOT, check=True)
print('Windows launcher built. Keep the whole app folder and its runtime directory.')
