"""Readable status colors and standard copy support shared by app tables."""
import json
from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QKeySequence, QAction
from PySide6.QtWidgets import QApplication, QTableWidget, QLabel

COLORS = {
    'success': ('#e5f3ec', '#206b4c'), 'pending': ('#fff3d9', '#88611b'),
    'running': ('#e5effb', '#325f92'), 'failed': ('#fae8e7', '#a43f40'),
    'stopped': ('#eeebf5', '#706185'), 'neutral': ('#eef1f3', '#536773'),
}


def color_item(item, state):
    bg, fg = COLORS.get(state, COLORS['neutral'])
    item.setBackground(QColor(bg))
    item.setForeground(QColor(fg))


def log_state(text):
    try:
        event = json.loads(text)
    except (ValueError, TypeError):
        event = {}
    if event.get('level') == 'error' or event.get('success') is False:
        return 'failed'
    if event.get('outcome') == 'registered' or event.get('event') in ('iclass.sign-success', 'selection.success'):
        return 'success'
    if event.get('level') in ('warn', 'warning'):
        return 'pending'
    low = text.lower()
    # Failure wins over a success word in a mixed line.
    if any(t in low for t in ('失败', '不明确', '未确认', 'error', 'failed', 'traceback')):
        return 'failed'
    if any(t in low for t in ('停止', '中断', 'stopped', 'interrupted')):
        return 'stopped'
    if any(t in low for t in ('等待', '未签到', '重试', '跳过', 'preview', '仅预览', 'attention', '待处理')):
        return 'pending'
    if any(t in low for t in ('成功', '已签到', 'completed')):
        return 'success'
    return 'running' if event or '运行' in text or '启动' in text else 'neutral'


class LogHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(COLORS[log_state(text)][1]))
        self.setFormat(0, len(text), fmt)


def copy_table(table):
    rows = {}
    for cell in table.selectedIndexes():
        item = table.item(cell.row(), cell.column())
        rows.setdefault(cell.row(), {})[cell.column()] = item.text() if item else ''
    QApplication.clipboard().setText('\n'.join('\t'.join(cols[c] for c in sorted(cols)) for _, cols in sorted(rows.items())))


class CopyFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.matches(QKeySequence.Copy):
            copy_table(obj)
            return True
        return False


def enable_copy(root):
    for item in root.findChildren(QLabel):
        item.setTextInteractionFlags(item.textInteractionFlags() | Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    for item in root.findChildren(QTableWidget):
        if getattr(item, '_copy_filter', None):
            continue
        item._copy_filter = CopyFilter(item)
        item.installEventFilter(item._copy_filter)
        action = QAction('复制所选行（Ctrl+C）', item)
        action.triggered.connect(lambda checked=False, table=item: copy_table(table))
        item.addAction(action)
        item.setContextMenuPolicy(Qt.ActionsContextMenu)
