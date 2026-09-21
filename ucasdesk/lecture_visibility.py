"""Shared rules for lecture display, reminders and calendar export."""
def visible_lecture(kind, row):
    location = row.get('location') or ''
    if ('雁栖湖' not in location or any(x in location for x in ('玉泉路', '中关村', '线上', '待定'))):
        return False
    return row.get('registrationStatus') in ('registered', 'not-required')
