"""Experimental anonymous course counts and a coalescing watch state machine."""
from dataclasses import dataclass
from html.parser import HTMLParser
import re

URL = 'https://jwba.ucas.ac.cn/sc/public/coursePublic'


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows = []; self.row = []; self.cell = None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row = []
        if tag in ('td', 'th'): self.cell = []
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip()); self.cell = None
        if tag == 'tr': self.rows.append(self.row); self.row = []


def parse_counts(html, code):
    """Only exact codes and named count columns; unknown layouts fail closed."""
    parser = Tables(); parser.feed(html)
    columns = None; found = []
    for row in parser.rows:
        names = [re.sub(r'\s+', '', cell) for cell in row]
        if '课程编码' in names and '已选人数' in names and '限选人数' in names:
            columns = [names.index(n) for n in ('课程编码', '已选人数', '限选人数')]
            continue
        if columns and len(row) > max(columns) and row[columns[0]].strip() == code:
            values = [row[i].strip() for i in columns[1:]]
            if not all(re.fullmatch(r'[0-9]+', v) for v in values):
                raise ValueError('公开人数格式不明确，保留原基线')
            found.append(tuple(map(int, values)))
    if len(found) != 1: raise ValueError('公开课程未唯一匹配或表头不支持，保留原基线')
    return found[0]


def query_counts(session, term, code):
    response = session.post(URL, data={'termId': term, 'courseCode': code}, timeout=(10, 20), allow_redirects=False)
    if response.status_code != 200: raise ValueError('公开查询返回非 200 状态，保留原基线')
    response.encoding = 'utf-8'
    return parse_counts(response.text, code)


@dataclass
class Baseline:
    count: int
    capacity: int
    observed_at: float
    last_signal: float


class Watch:
    def __init__(self, codes, initial=False, fallback=3600):
        self.codes = tuple(codes); self.initial = initial; self.fallback = fallback
        self.baselines = {}; self.pending = set(); self.blocked = set(); self.running = None

    def observe(self, code, count, capacity, now):
        old = self.baselines.get(code)
        signal = (old is None and self.initial and count < capacity) or (old is not None and
            (count < old.count or (self.fallback > 0 and count < capacity and now-old.last_signal >= self.fallback)))
        self.baselines[code] = Baseline(count, capacity, now, now if signal or old is None else old.last_signal)
        if signal and code not in self.blocked and code != self.running: self.pending.add(code)

    def take(self):
        if self.running is not None: return None
        for code in self.codes:
            if code in self.pending and code not in self.blocked:
                self.pending.remove(code); self.running = code; return code
        return None

    def finish(self, code, outcome):
        # No terminal proof of unavailability means no automatic resubmission.
        if outcome != 'unavailable': self.blocked.add(code)
        self.pending.discard(code); self.running = None
