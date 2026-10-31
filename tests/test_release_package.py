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
            for name in packaging.FILES:
                path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic')
            (base/'action.json').write_text(json.dumps({'version':'1.0.0'}))
            (base/'private.jpg').write_text('private')
            (base/'.env').write_text('secret')
            archive=packaging.build(root,'v1.0.0');first=archive.read_bytes()
            self.assertEqual(archive.with_suffix('.zip.sha256').read_text(),hashlib.sha256(first).hexdigest()+'  '+archive.name+'\n')
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()),{'actions/analog-meter-reading/'+n for n in packaging.FILES})
            self.assertEqual(packaging.build(root,'v1.0.0').read_bytes(),first)
            with self.assertRaises(ValueError):packaging.build(root,'v2.0.0')
            (base/'ui/editor.js').unlink()
            with self.assertRaises(ValueError):packaging.build(root,'v1.0.0')
