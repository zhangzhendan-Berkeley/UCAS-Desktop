"""Apply the portable installer's strict patch chain to the pinned clean source."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ucasdesk.portable import prepare_lecture
raw = subprocess.check_output(['git', 'archive', '--format=zip', 'HEAD'], cwd=ROOT / 'vendor/ucas-humanity-lecture-bot')
with tempfile.TemporaryDirectory() as tmp:
    dest = Path(tmp)
    zipfile.ZipFile(io.BytesIO(raw)).extractall(dest)
    prepare_lecture(ROOT, dest)
    assert 'scienceMode: z.boolean().optional()' in (dest / 'src/config.ts').read_text()
    assert 'if (config.scienceMode && config.onePerStartTime)' in (dest / 'src/workflow.ts').read_text()
    assert 'departmentCell.includes("本科部")' in (dest / 'src/lecture-page.ts').read_text()
    assert 'executablePath: process.env.UCAS_BROWSER_EXECUTABLE' in (dest / 'src/workflow.ts').read_text(encoding='utf-8')
print('Portable strict patch chain: PASS')
