import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('packaging', ROOT/'scripts/package_release.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


class ReleasePackage(unittest.TestCase):
    def test_allowlist_digest_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'actions/analog-meter-reading';base.mkdir(parents=True)
            for action, names in packaging.ACTION_FILES.items():
                for name in names:
                    path=root/'actions'/action/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic')
                (root/'actions'/action/'action.json').write_text(json.dumps({'version':'1.0.0'}))
            (base/'private.jpg').write_text('private')
            (base/'.env').write_text('secret')
            archive=packaging.build(root,'v1.0.0');first=archive.read_bytes()
            self.assertEqual(archive.with_suffix('.zip.sha256').read_text(),hashlib.sha256(first).hexdigest()+'  '+archive.name+'\n')
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()),{'actions/'+action+'/'+n for action,names in packaging.ACTION_FILES.items() for n in names})
            self.assertEqual(packaging.build(root,'v1.0.0').read_bytes(),first)
            with self.assertRaises(ValueError):packaging.build(root,'v2.0.0')
            leak=root/'actions/water-leak-detection/action.json'
            leak.write_text(json.dumps({'version':'0.9.0'}))
            with self.assertRaises(ValueError):packaging.build(root,'v1.0.0')
            leak.write_text(json.dumps({'version':'1.0.0'}))
            (base/'ui/editor.js').unlink()
            with self.assertRaises(ValueError):packaging.build(root,'v1.0.0')
