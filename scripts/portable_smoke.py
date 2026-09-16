"""Run only in a disposable extracted portable package, with a clean PATH."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    assert (ROOT / 'portable-version.json').exists(), 'Only test a disposable portable package'
    assert Path(sys.executable).resolve().is_relative_to(ROOT / 'runtime/python')
    assert str(ROOT) in sys.path, 'Embedded interpreter must find app modules without injected paths'
    assert all(Path(p).resolve().is_relative_to(ROOT) for p in sys.path if p), sys.path
    # Check the OCR subprocess before Qt adds any DLL directories to the parent.
    subprocess.run([sys.executable, '-c', '''import ddddocr, ctypes, sys
from pathlib import Path
ddddocr.DdddOcr(show_ad=False)
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];k.GetModuleHandleW.restype=ctypes.c_void_p
k.GetModuleFileNameW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint]
handle=k.GetModuleHandleW('msvcp140.dll');assert handle
buffer=ctypes.create_unicode_buffer(32768);assert k.GetModuleFileNameW(handle,buffer,len(buffer))
assert Path(buffer.value).resolve().parent==Path(sys.executable).resolve().parent, 'OCR used external MSVC runtime'
print('Standalone OCR with bundled MSVC: PASS')
'''], check=True)
    for name in ('PySide6.QtWidgets', 'PySide6.QtSvg', 'openpyxl', 'pandas', 'reportlab',
                 'requests', 'qrcode', 'selenium', 'ddddocr', 'numpy', 'PIL', 'onnxruntime',
                 'cv2', 'dotenv', 'chromedriver_autoinstaller'):
        importlib.import_module(name)
    import ddddocr
    from PIL import Image
    import io
    buffer = io.BytesIO()
    Image.new('RGB', (120, 40), 'white').save(buffer, format='PNG')
    ddddocr.DdddOcr(show_ad=False).classification(buffer.getvalue())
    from ucasdesk.core import PYTHON, NODE, child_env, protect
    assert protect(protect(b'portable-fixture'), decrypt=True) == b'portable-fixture'
    assert PYTHON == ROOT / 'runtime/python/python.exe'
    assert NODE == ROOT / 'runtime/node/node.exe'
    subprocess.run([str(PYTHON), '-c', 'print("portable child: OK")'], check=True, env=child_env())
    subprocess.run([str(NODE), '--version'], check=True, env=child_env())
    subprocess.run([str(NODE), '--input-type=module', '-e',
                    "import('./adapters/mooc_helpers.mjs').then(()=>console.log('mooc import: OK'))"], cwd=ROOT, check=True, env=child_env())
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from ucasdesk.ui import Window, STYLE, load_fonts
    app = QApplication([])
    app.setStyle('Fusion')
    load_fonts()
    app.setStyleSheet(STYLE)
    errors = []
    sys.excepthook = lambda kind, value, tb: errors.append(str(value))
    window = Window()
    window.error = errors.append
    try:
        window.load_planner()
        assert window.planner, errors
        assert len(window.planner.catalog.courses) == 2090
        assert window.planner.course_table.rowCount() == 1499
        assert not window.vault.secret_values()
        window.show()
        app.processEvents()
        assert not errors, errors
    finally:
        window.request_exit()
    print(json.dumps({'portable_smoke': 'pass', 'python': sys.version.split()[0],
                      'courses': 2090, 'ocr': 'pass', 'gui': 'pass', 'node': 'pass', 'school_requests': 0}))


if __name__ == '__main__': main()
