import os
import sys
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ['PYTHONIOENCODING'] = 'utf-8'

def main():
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('UCAS.DesktopAssistant')
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtGui import QIcon
    from ucasdesk.instance import server_name, activate_existing, InstanceServer
    from ucasdesk.core import DATA
    from ucasdesk.ui import Window, STYLE, load_fonts
    application = QApplication(sys.argv)
    application.setApplicationName('UCAS Desktop')
    application.setWindowIcon(QIcon(str(ROOT / 'assets/app.ico')))
    application.setStyle('Fusion')
    load_fonts()
    application.setStyleSheet(STYLE)
    lock = QLockFile(str(DATA / 'app.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if not activate_existing(server_name(DATA)):
            QMessageBox.information(None, 'UCAS 桌面助手', '应用正在启动，请稍后再次打开；也可以点击任务栏右下角的托盘图标。')
        return 0
    window = Window()
    instance = InstanceServer(server_name(DATA), window.show_window, application)
    application.aboutToQuit.connect(window.shutdown)
    application.aboutToQuit.connect(instance.close)
    application.commitDataRequest.connect(lambda _: window.shutdown())
    window.show()
    if '--smoke-test' in sys.argv:
        QTimer.singleShot(100, window.load_planner)
        def finish_smoke():
            import json
            report = {'planner_loaded': window.planner is not None, 'python': sys.executable}
            (ROOT / 'logs/launcher-smoke.json').write_text(json.dumps(report), encoding='utf-8')
            window.request_exit()
        QTimer.singleShot(4000, finish_smoke)
    return application.exec()

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        (ROOT / 'logs').mkdir(exist_ok=True)
        (ROOT / 'logs/startup-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        if sys.stderr:
            traceback.print_exc()
        raise
