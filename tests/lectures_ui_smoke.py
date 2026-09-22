"""Read-only, isolated window integration; real popup and reminder timer dispatch."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QCheckBox
from ucasdesk.ui import Window,style_sheet,load_fonts
from ucasdesk.core import Store,read_json
from ucasdesk.activity import scope
from ucasdesk.automation import Automation
from ucasdesk.lecture_reminders import now_beijing
from tests.vault_fixture import isolated_keychain

app=QApplication([]);load_fonts();app.setStyleSheet(style_sheet())
with isolated_keychain(),tempfile.TemporaryDirectory() as tmp:
 directory=Path(tmp)
 def engine(jobs,vault,parent):
  result=Automation(jobs,vault,parent,directory=directory);result.timer.stop();return result
 with patch('ucasdesk.ui.DATA',directory),patch('ucasdesk.core.DATA',directory),patch('ucasdesk.ui.Store',lambda:Store(directory/'tasks.db')),patch('ucasdesk.ui.Automation',engine),patch('ucasdesk.ui.LocalAPI',side_effect=OSError('offline')):
  w=Window();w.lecture_timer.stop();w.clock.stop();errors=[];w.error=errors.append
  try:
   w.account_fields['sep'][0].setText('fixture-student');w.account_fields['sep'][1].setText('fixture-password');w.save_profile('sep')
   account=scope(w.vault,'sep');now=now_beijing().replace(hour=9,minute=0,second=0,microsecond=0)
   for kind,title in [('humanity','美与文明：艺术中的时代记忆'),('science','从基础研究到科学前沿：探索未知的边界')]:
    w.activity.snapshot(account,'calendar-'+kind,{'rows':[{'title':title,'registrationStatus':'registered','department':'研究生学院','start':(now+timedelta(minutes=15)).isoformat(),'end':(now+timedelta(hours=2)).isoformat(),'location':'雁栖湖校区 · 国际会议中心报告厅'}]})
   w.activity.snapshot(account,'attendance',{'humanity':{'total':3,'valid':2,'hours':4},'science':{'total':2,'valid':2,'hours':5}})
   w.nav.setCurrentRow(next(i for i in range(w.nav.count()) if w.nav.item(i).text() == '人文/科研讲座'))
   with patch('ucasdesk.lectures.now_beijing',return_value=now):
    w.refresh_today_lectures()
    assert w.nav.currentItem().text()=='人文/科研讲座'
    assert '还差 15 学时' in w.lecture_progress['science'][1].text()
    assert len(w.lecture_scroll.findChildren(QCheckBox))==2
    w.lecture_remind_enabled.setChecked(True);w.lecture_remind_minutes.setValue(25)
    assert read_json(directory/'lecture-reminders.json')['accounts'][account]['minutes']==25
    w.show();app.processEvents()
    target=Path('logs/previews/desktop-today-lectures.png');target.parent.mkdir(parents=True,exist_ok=True);w.grab().save(str(target))
    w.hide()
    with patch.object(w,'show_lecture_popup') as notify,patch('ucasdesk.lecture_reminders.now_beijing',return_value=now):
     w.lecture_tick();assert notify.call_count==1;assert len(notify.call_args.args[0])==2
     w.lecture_tick();assert notify.call_count==1
    w.test_lecture_popup();app.processEvents();assert w._lecture_popups[-1].isVisible()
    w._lecture_popups[-1].close();app.processEvents()
   assert not hasattr(w,'lecture_id'),'Removed lecture sign-in entry'
   with patch.object(w,'start_job',return_value='fixture') as job:
    w.refresh_lecture_information();assert job.call_args.args[4]['preview'] is True
   # Unknown hours cannot be displayed as zero or an achieved goal.
   w.activity.snapshot(account,'attendance',{'science':{'total':2,'valid':2,'hours':None}});w.refresh_today_lectures()
   assert '未获取' in w.lecture_progress['science'][1].text()
  finally:w._quitting=True;w.close()
print('Today lecture layout, progress, settings, hidden-window dispatch and dedup: PASS')
