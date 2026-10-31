import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'actions/analog-meter-reading'))
from report import Report


class ReportTests(unittest.TestCase):
    def test_pagination_stays_inside_private_preview_image_limits(self):
        report = Report()
        for i in range(73):report.add(f'Step {i}', Image.new('RGB', (32,32)), 'Accepted')
        with tempfile.TemporaryDirectory() as directory:
            report.save(Path(directory)/'recognition-report.jpg', {'status':'read','readings':[]})
            pages=sorted(Path(directory).glob('*.jpg'))
            self.assertEqual(len(pages),2)
            for page in pages:
                with Image.open(page) as image:
                    self.assertLessEqual(image.height,8192)
                    self.assertLess(image.width*image.height,16_000_000)
                self.assertLess(page.stat().st_size,8*1024*1024)
