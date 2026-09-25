"""Offline installation check; never opens a school page or reads account values."""
import argparse,json,subprocess,sys,importlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ucasdesk.core import NODE,child_env
from ucasdesk.portable import module_issues
from ucasdesk import __version__

def check(root=ROOT):
    errors=[]
    for name in ('PySide6.QtWidgets','requests','selenium','ddddocr','coursesystem'):
        if name=='coursesystem':sys.path.insert(0,str(root/'vendor/UCAS-Course-Selector/src'))
        try:importlib.import_module(name)
        except Exception as exc:errors.append(name+': '+type(exc).__name__)
    modules=json.loads((root/'modules.json').read_text(encoding='utf-8'))
    for module in modules:
        if module.get('external_opt_in') and not (root/module['path']).exists():
            print(module['id']+': optional, not installed');continue
        missing=module_issues(root,module)
        if missing:errors.append(module['id']+': '+', '.join(missing))
        else:print(module['id']+': ready')
    imports=['./adapters/mooc_helpers.mjs','./adapters/mooc_course.mjs']
    if (root/'vendor/ucas-humanity-lecture-bot').exists():imports+=['./vendor/ucas-humanity-lecture-bot/dist/src/workflow.js']
    code=';'.join('await import('+json.dumps(p)+')' for p in imports)
    try:subprocess.run([str(NODE),'--input-type=module','-e',code],cwd=root,env=child_env(),check=True,timeout=30,capture_output=True)
    except (OSError,subprocess.SubprocessError):errors.append('Node component import failed; run component repair')
    print('Version:',__version__)
    for error in errors:print('FAIL:',error)
    return not errors

if __name__=='__main__':raise SystemExit(0 if check() else 1)
