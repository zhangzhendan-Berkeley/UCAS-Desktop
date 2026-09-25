"""Copy private data into a new installation while both apps are stopped."""
import argparse
from pathlib import Path
import shutil,sys
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def migrate(source,target):
    from PySide6.QtCore import QLockFile
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target or source.is_relative_to(target) or target.is_relative_to(source):raise ValueError('新旧安装目录必须互不包含。')
    if not (source/'app.py').is_file() or not (source/'data').is_dir() or not (target/'app.py').is_file():raise ValueError('请选择完整的 UCAS 桌面助手文件夹。')
    (target/'data').mkdir(exist_ok=True)
    locks=[]
    try:
        for root in (source,target):
            lock=QLockFile(str(root/'data/app.lock'));lock.setStaleLockTime(0)
            if not lock.tryLock(100):raise RuntimeError('请先从托盘退出新旧程序，再迁移数据。')
            locks.append(lock)
        backup=target/'data/migration-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        changed=[]
        try:
            for incoming in (source/'data').rglob('*'):
                relative=incoming.relative_to(source/'data')
                if any(p in ('update-backups','migration-backups','module-backups','module-downloads') for p in relative.parts) or incoming.name=='app.lock':continue
                if incoming.is_symlink():raise ValueError('数据目录含符号链接，请手动核对。')
                if not incoming.is_file():continue
                dest=target/'data'/relative;saved=backup/relative
                existed=dest.exists()
                if existed:saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
                dest.parent.mkdir(parents=True,exist_ok=True)
                temporary=dest.with_name(dest.name+'.migrate-tmp');shutil.copy2(incoming,temporary);temporary.replace(dest);changed.append((dest,saved,existed))
        except Exception:
            for dest,saved,existed in reversed(changed):
                if existed:shutil.copy2(saved,dest)
                else:dest.unlink()
            raise
        return len(changed)
    finally:
        for lock in reversed(locks):lock.unlock()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path);parser.add_argument('--target',type=Path,default=ROOT);args=parser.parse_args()
    app=None
    if args.source is None:
        from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
        app=QApplication([])
        value=QFileDialog.getExistingDirectory(None,'选择旧版 UCAS 桌面助手文件夹（包含 app.py 和 data）')
        if not value:return
        args.source=Path(value)
    try:
        count=migrate(args.source,args.target)
        message=f'已迁移 {count} 个数据文件，旧安装保持不变。请从新文件夹启动应用。Windows 密码需在原 Windows 用户下读取。'
        if app:QMessageBox.information(None,'迁移完成',message)
        else:print(message)
    except Exception as exc:
        if app:QMessageBox.warning(None,'迁移未完成',str(exc))
        else:print(str(exc),file=sys.stderr)
        raise SystemExit(1)

if __name__=='__main__':main()
