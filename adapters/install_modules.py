"""One-click installation of fixed external modules; never logs into school systems."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucasdesk.core import ROOT, read_json
from ucasdesk.portable import install_module


if __name__ == '__main__':
    try:
        options = json.load(sys.stdin)
        requested = set(options.get('modules', ['lecture', 'selection']))
        if not requested <= {'lecture', 'selection'}:
            raise ValueError('不支持的模块')
        manifest = read_json(ROOT / 'runtime/modules-downloads.json')
        for module in read_json(ROOT / 'modules.json', []):
            if module['id'] in requested:
                install_module(ROOT, module, manifest)
        print('组件准备完成，可返回对应页面使用。未运行任何学校任务。', flush=True)
    except Exception as exc:
        print('组件准备未完成：' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
