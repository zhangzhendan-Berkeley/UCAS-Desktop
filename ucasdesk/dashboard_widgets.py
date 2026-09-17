"""Selectable, structured dashboard cards with explicit information hierarchy."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy


def text_label(text='', name=''):
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return label


class StatusCard(QFrame):
    def __init__(self, title, accent, action, callback):
        super().__init__()
        self.setObjectName('statusCard')
        self._title, self.accent = title, accent
        self._rows, self._detail = [], 'detailed'
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 17, 20, 14)
        box.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(text_label(title, 'cardTitle'), 1)
        self.badge = text_label('', 'cardBadge')
        self.badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        header.addWidget(self.badge)
        box.addLayout(header)
        self.headline = text_label('', 'cardHeadline')
        box.addWidget(self.headline)
        self.details = QVBoxLayout()
        self.details.setSpacing(8)
        box.addLayout(self.details)
        box.addStretch(1)
        self.note = text_label('', 'cardNote')
        box.addWidget(self.note)
        self.action = QPushButton(action + '  →')
        self.action.setObjectName('cardAction')
        self.action.clicked.connect(callback)
        box.addWidget(self.action, 0, Qt.AlignLeft)

    def title(self):
        return self._title

    def set_content(self, headline, rows=(), note='', badge=''):
        self.headline.setText(headline)
        self.badge.setText(badge)
        self.badge.setVisible(bool(badge))
        self.note.setText(note)
        # Refreshes run every five seconds: retain widgets and their text selection.
        values = list(rows)
        while len(self._rows) < len(values):
            label = text_label('', 'cardDetail')
            self.details.addWidget(label)
            self._rows.append(label)
        for index, label in enumerate(self._rows):
            value = values[index] if index < len(values) else ''
            if label.text() != value: label.setText(value)
        self.configure_detail(self._detail)

    def configure_detail(self, detail):
        self._detail = detail
        limit = {'compact': 0, 'normal': 2, 'detailed': 100}.get(detail, 100)
        for index, label in enumerate(self._rows):
            label.setVisible(index < limit and bool(label.text()))
        self.note.setVisible(detail != 'compact' and bool(self.note.text()))
        full = '\n'.join([self.headline.text()] + [r.text() for r in self._rows if r.text()] + [self.note.text()])
        self.setToolTip(full)

    def text(self):
        values = [self.headline.text()]
        if self._detail != 'compact':
            limit = 2 if self._detail == 'normal' else 100
            values += [r.text() for r in self._rows[:limit] if r.text()]
            if self.note.text(): values.append(self.note.text())
        return '\n'.join(values)

    def configure_color(self, color):
        values = [((c / 255 + .055) / 1.055) ** 2.4 if c / 255 > .04045 else c / 255 / 12.92
                  for c in (color.red(), color.green(), color.blue())]
        light = sum(a*b for a,b in zip(values, (.2126, .7152, .0722))) > .3
        fg, muted = ('#19352f', '#405b52') if light else ('#ffffff', '#e0e8e4')
        accent = self.accent if light else '#ffffff'
        self.setStyleSheet(f'''
            QFrame#statusCard {{background:{color.name()}; border:1px solid {color.darker(110).name()}; border-radius:14px;}}
            QFrame#statusCard QLabel {{background:transparent; color:{fg}; border:0;}}
            QLabel#cardTitle {{font-size:13px; font-weight:600; color:{muted};}}
            QLabel#cardHeadline {{font-size:20px; font-weight:700; padding:2px 0;}}
            QLabel#cardDetail {{font-size:13px;}}
            QLabel#cardNote {{font-size:11px; color:{muted}; padding-top:4px;}}
            QLabel#cardBadge {{color:{accent}; font-size:11px; font-weight:600; padding:4px 8px; border:1px solid {color.darker(120).name()}; border-radius:8px;}}
            QPushButton#cardAction {{background:transparent; color:{accent}; font-weight:600; border:0; padding:3px 0; text-align:left;}}
            QPushButton#cardAction:hover {{text-decoration:underline;}}
        ''')


class StatTile(QFrame):
    def __init__(self, title, unit, accent):
        super().__init__()
        self.setObjectName('statTile')
        self.unit = unit
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 13, 18, 13)
        box.setSpacing(4)
        self.value = text_label('0 ' + unit, 'statValue')
        box.addWidget(self.value)
        box.addWidget(text_label(title, 'statTitle'))
        self.setStyleSheet(f'''QFrame#statTile {{background:#ffffff; border:1px solid #d8e2dc; border-radius:12px;}}
            QFrame#statTile QLabel {{background:transparent; border:0;}}
            QLabel#statValue {{font-size:25px; font-weight:700; color:{accent};}}
            QLabel#statTitle {{font-size:12px; color:#536b60;}}''')

    def set_value(self, value):
        self.value.setText(f'{value} {self.unit}')
