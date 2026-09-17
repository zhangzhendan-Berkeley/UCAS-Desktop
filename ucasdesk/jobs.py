from __future__ import annotations
import codecs
import json
import os
import subprocess
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from .core import ROOT, LOGS, child_env, redact
from .enrollment import account_hash


class Jobs(QObject):
    changed = Signal()
    output = Signal(str, str)
    ended = Signal(str, object)

    def __init__(self, store, vault):
        super().__init__()
        self.store, self.vault = store, vault
        self.active = {}

    def start(self, module, title, program, args, payload=None, cwd=ROOT, extra_env=None):
        if any(x['module'] == module or (module in ('lecture', 'lecture-clock') and x['module'] in ('lecture', 'lecture-clock')) for x in self.active.values()):
            raise RuntimeError('此模块已有运行中的任务，请先在“任务与日志”停止原任务。')
        ids = set()
        if module in ('iclass', 'iclass-daily', 'iclass-manual', 'lecture-sign') and payload:
            ids = {str(c['id']) for c in payload.get('courses', [])}
            if payload.get('identifier'):
                ids.add(payload['identifier'])
            if any(ids & item.get('course_ids', set()) for item in self.active.values()):
                raise RuntimeError('该排课已在其他签到任务中，未重复建立。')
        job_id = self.store.create(module, title)
        proc = QProcess(self)
        proc.setWorkingDirectory(str(cwd))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        environment = QProcessEnvironment()
        for key, value in child_env(extra_env).items():
            environment.insert(key, str(value))
        proc.setProcessEnvironment(environment)
        values = self.vault.secret_values()
        if payload:
            values.extend(str(payload.get(k, '')) for k in ('username', 'password'))
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.active[job_id] = {'process': proc, 'module': module, 'stopping': False, 'decoder': decoder, 'secrets': values, 'buffer': '', 'course_ids': ids,
            'account': account_hash(payload['username']) if payload and payload.get('username') else '',
            'preview': bool((payload or {}).get('preview')), 'semester': (payload or {}).get('semester', ''), 'title': title}
        proc.readyReadStandardOutput.connect(lambda: self.drain(job_id))
        proc.finished.connect(lambda code, status: self.finished(job_id, code))
        proc.errorOccurred.connect(lambda error: self.failed(job_id, error))
        if payload is not None:
            def send():
                proc.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
                proc.closeWriteChannel()
            proc.started.connect(send)
        proc.start(str(program), [str(arg) for arg in args])
        self.changed.emit()
        return job_id

    def log(self, job_id, text):
        active = self.active.get(job_id, {})
        clean = redact(text, active.get('secrets', self.vault.secret_values()))
        with (LOGS / f'{job_id}.log').open('a', encoding='utf-8') as handle:
            handle.write(clean)
        self.output.emit(job_id, clean)

    def drain(self, job_id, final=False):
        item = self.active.get(job_id)
        if item:
            raw = bytes(item['process'].readAllStandardOutput())
            item['buffer'] += item['decoder'].decode(raw, final=final)
            if final:
                self.log(job_id, item['buffer'])
                item['buffer'] = ''
            elif '\n' in item['buffer']:
                complete, item['buffer'] = item['buffer'].rsplit('\n', 1)
                self.log(job_id, complete + '\n')

    def failed(self, job_id, error):
        if error == QProcess.FailedToStart and job_id in self.active:
            self.log(job_id, '进程启动失败，请检查运行环境。\n')
            self.store.status(job_id, 'failed')
            item = self.active.pop(job_id)
            self.ended.emit(job_id, {key: item.get(key) for key in ('module', 'account', 'preview', 'title')} | {'status': 'failed', 'code': None})
            item['process'].deleteLater()
            self.changed.emit()

    def finished(self, job_id, code):
        if job_id not in self.active:
            return
        self.drain(job_id, final=True)
        item = self.active.pop(job_id)
        status = 'stopped' if item['stopping'] else ('completed' if code == 0 else 'attention' if item['module'] == 'mooc' and code == 2 else 'failed')
        self.store.status(job_id, status)
        self.ended.emit(job_id, {key: item.get(key) for key in ('module', 'account', 'preview', 'title')} | {'status': status, 'code': code})
        self.log(job_id, f'\n任务结束：{status}（退出码 {code}）。请查看上方各项实际结果。\n')
        item['process'].deleteLater()
        self.changed.emit()

    def stop(self, job_id):
        item = self.active.get(job_id)
        if not item:
            return
        item['stopping'] = True
        self.store.status(job_id, 'stopping')
        pid = item['process'].processId()
        if pid:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            else:
                item['process'].kill()
        item['process'].kill()
        self.changed.emit()

    def stop_all(self):
        for job_id in list(self.active):
            self.stop(job_id)
        for item in list(self.active.values()):
            item['process'].waitForFinished(3000)
