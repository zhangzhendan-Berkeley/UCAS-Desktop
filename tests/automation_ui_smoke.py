"""Exercise save/restore/stop UI without credentials or school requests."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from ucasdesk.ui import Window, STYLE, load_fonts
from ucasdesk.automation import Automation
from ucasdesk.core import Store, ROOT


class FakeVault:
    warning = ''
    def __init__(self): self.accounts = {}
    def get(self, key): return self.accounts.get(key, {'username': '', 'password': ''})
    def set(self, key, username, password, remember=False): self.accounts[key] = dict(username=username, password=password)
    def secret_values(self): return ['fixture-password']


app = QApplication([])
load_fonts()
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    def engine(jobs, vault, parent):
        result = Automation(jobs, vault, parent, directory=directory)
        result.timer.stop()
        return result
    with patch('ucasdesk.ui.Vault', FakeVault), patch('ucasdesk.ui.Store', lambda: Store(directory / 'jobs.db')), \
         patch('ucasdesk.ui.Automation', engine), patch('ucasdesk.ui.LocalAPI', side_effect=OSError('offline')):
        window = Window()
        errors = []
        window.error = errors.append
        try:
            window.resize(1380, 1000)
            for key in ('iclass', 'sep'):
                fields = window.account_fields[key]
                fields[0].setText('fixture-user')
                fields[1].setText('fixture-password')
                fields[2].setChecked(True)
            with patch.object(window.jobs, 'start', return_value='fixture') as start:
                window.daily_enabled.setChecked(True)
                window.save_daily_plan()
                assert window.automation.enabled('course')
                window.lecture_clock.setChecked(True)
                window.lecture_book.setChecked(True)
                window.lecture_hours.setText('8,9,18')
                window.save_lecture_plan()
                assert window.automation.config['lecture']['hours'] == [8, 9, 18]
                assert window.automation.config['lecture']['book']
                assert 'fixture-password' not in window.automation.path.read_text()
                assert not errors, errors
                window.show()
                window.nav.setCurrentRow(2)
                app.processEvents()
                window.grab().save(str(ROOT / 'docs/desktop-automation.png'))
                assert window.lecture_clock_status.geometry().bottom() < window.pages.height()
                window.stop_all_tasks()
                assert not window.automation.enabled('course')
                assert not window.automation.enabled('lecture')
                assert not window.daily_enabled.isChecked()
                assert not window.lecture_clock.isChecked()
            print('Automation UI save, credentials isolation, restore config, stop and layout: PASS')
        finally:
            window.request_exit()
