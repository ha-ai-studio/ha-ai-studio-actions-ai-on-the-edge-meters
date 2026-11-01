"""Package only explicitly approved runtime files, including the built editor."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

FILES = (
    'action.json', 'action.py', 'capture.py', 'correction.py', 'report.py',
    'engine.py', 'number_block.py', 'requirements.lock', 'LICENSE.md', 'THIRD_PARTY.md',
    'models/dig-cont_0900_s3_q.tflite', 'models/ana-cont_1500_s2_q.tflite',
    'models/PROVENANCE.json', 'ui/editor.js', 'ui/editor.css',
)


ACTION_FILES = {
    'analog-meter-reading': FILES,
    'water-leak-detection': ('action.json', 'action.py', 'requirements.lock', 'LICENSE.md', 'README.md'),
}

def build(root, tag):
    files = []
    for action, names in ACTION_FILES.items():
        base = root / 'actions' / action
        version = json.loads((base / 'action.json').read_text())['version']
        if tag != 'v' + version:
            raise ValueError('Release tag must match every action.json version prefixed with v.')
        files.extend(base / name for name in names)
    for path in files:
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents) if p == root or root in p.parents):
            raise ValueError('Required runtime file missing or symlink: ' + path.name)
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError('Runtime file exceeds Studio size limit.')
    if sum(p.stat().st_size for p in files) > 32 * 1024 * 1024:
        raise ValueError('Package exceeds Studio size limit.')
    out = root / 'dist'
    out.mkdir(exist_ok=True)
    archive = out / 'ha-ai-studio-actions.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n')
    return archive


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parents[1], sys.argv[1]))
