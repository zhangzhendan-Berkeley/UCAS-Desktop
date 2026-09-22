"""Shared rules for lecture display, reminders and calendar export."""
def visible_lecture(kind, row):
    if kind == 'science' and '本科部' in ''.join(str(row.get('department') or '').split()):
        return False
    location = row.get('location') or ''
    if ('雁栖湖' not in location or any(x in location for x in ('玉泉路', '中关村', '线上', '待定'))):
        return False
    return row.get('registrationStatus') in ('registered', 'not-required')


def calendar_lecture(kind, row):
    """Include booked and explicitly registration-free events; exclude undergraduate science."""
    return visible_lecture(kind, row)
