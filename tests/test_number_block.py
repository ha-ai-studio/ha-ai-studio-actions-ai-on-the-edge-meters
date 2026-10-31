import copy
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'actions/analog-meter-reading'))
import numpy as np
from PIL import Image, ImageDraw
from number_block import recognize
import test_analog_meter_reading as existing_tests
from engine import run, resolve_layouts, ReadingError


class NumberBlockTests(unittest.TestCase):
    def image(self):
        image = Image.new('RGB', (500, 110), 'white')
        ImageDraw.Draw(image).text((20, 15), '00123456', fill='black', font_size=72)
        return image

    def test_real_tesseract_preserves_leading_zeros(self):
        self.assertEqual(recognize(self.image(), 8, '00123456'), '00123456')

    def test_real_tesseract_dark_and_uneven_illumination(self):
        pixels = np.asarray(self.image(), dtype=np.float32)
        width = pixels.shape[1]
        for light in (np.full(width, 0.22), np.linspace(0.15, 0.7, width)):
            with self.subTest(min_light=float(light.min())):
                shaded = Image.fromarray(np.clip(pixels * light[None, :, None] + 8, 0, 255).astype(np.uint8))
                self.assertEqual(recognize(shaded, 8, '00123456'), '00123456')

    def test_real_tesseract_blank_dark_image_is_not_a_number(self):
        with self.assertRaisesRegex(ValueError, 'could not'):
            recognize(Image.new('RGB', (400, 90), (28, 32, 25)))

    def test_disagreement_length_comparison_and_invalid_text(self):
        for outputs, length, expected, message in [
            ([b'00123456', b'00123457'], 8, None, 'disagree'),
            ([b'00123456'] * 2, 7, None, 'length'),
            ([b'00123456'] * 2, 8, '00123457', 'expected value'),
            ([b'abc'], None, None, 'could not'),
            ([b''], None, None, 'could not'),
            ([b'1' * 33], None, None, 'could not'),
        ]:
            with self.subTest(message=message), patch('number_block.subprocess.run', side_effect=[subprocess.CompletedProcess([], 0, x) for x in outputs]):
                with self.assertRaisesRegex(ValueError, message):
                    recognize(self.image(), length, expected)

    def test_runtime_failures_and_budget(self):
        for error, message in [(FileNotFoundError(), 'requires Tesseract'), (subprocess.TimeoutExpired('tesseract', 8), 'timed out'), (subprocess.CalledProcessError(1, 'tesseract', stderr=b'private diagnostic'), 'OCR failed')]:
            with self.subTest(message=message), patch('number_block.subprocess.run', side_effect=error):
                with self.assertRaisesRegex(ValueError, message):recognize(self.image())
        with patch('number_block.subprocess.run') as process:
            with self.assertRaisesRegex(ValueError, 'timed out'):recognize(self.image(), deadline=time.monotonic()-1)
            process.assert_not_called()

    def test_second_variant_uses_remaining_deadline(self):
        with patch('number_block.time.monotonic', side_effect=[101, 108]), patch('number_block.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'00123456')) as process:
            self.assertEqual(recognize(self.image(), deadline=110), '00123456')
        self.assertEqual([call.kwargs['timeout'] for call in process.call_args_list], [8, 2])

    def test_invalid_configuration(self):
        for length, expected in [(0, None), (True, None), (33, None), (8, '123'), (None, '12.3')]:
            with self.subTest(length=length, expected=expected), patch('number_block.subprocess.run') as process:
                with self.assertRaises(ValueError):recognize(self.image(), length, expected)
                process.assert_not_called()


class NumberBlockPipelineTests(unittest.TestCase):
    def setUp(self):
        fixture = existing_tests.EngineTests()
        fixture.setUp()
        self.fixture = fixture
        self.addCleanup(fixture.doCleanups)
        self.context, self.data, self.settings = fixture.context, fixture.data, fixture.settings
        self.settings['regions'] = self.settings['regions'][:3]
        self.settings['regions'][2].update(kind='number_block', expected_length=8)
        self.settings['meters'][0]['layout'] = ['digit-a']

    def test_text_result_preview_and_settings_preserved(self):
        before = copy.deepcopy(self.settings)
        with patch('engine.recognize_number_block', return_value='00123456'):
            result = run(self.data, self.settings, self.context, preview=True)
        self.assertEqual(result['readings'][0]['value'], '00123456')
        self.assertEqual(result['readings'][0]['raw_value'], '00123456')
        self.assertEqual(result['status'], 'read')
        self.assertIsNone(result['regions'][0]['fit'])
        self.assertTrue((Path(self.context['output_dir']) / result['regions'][0]['image']).is_file())
        self.assertEqual(before, self.settings)

    def test_actual_ocr_through_cropped_aligned_preview(self):
        image = self.fixture.image.copy()
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 100, 530, 210), fill='white')
        draw.text((115, 115), '00123456', fill='black', font_size=65)
        ident = self.fixture.save_image(image)
        self.settings['reference']['asset_id'] = ident
        self.settings['regions'][2].update(x=100, y=100, width=430, height=110, expected_value='00123456')
        self.settings['crop'] = dict(x=15, y=15, width=600, height=410)
        result = run({'image': {'asset_id': ident}}, self.settings, self.context, preview=True)
        self.assertEqual(result['status'], 'read')
        self.assertEqual(result['readings'][0]['value'], '00123456')
        report = Path(self.context['output_dir']) / 'recognition-report-01.jpg'
        self.assertTrue(report.is_file())
        with Image.open(report) as diagnostic:
            self.assertEqual(diagnostic.width, 1180)
            self.assertLessEqual(diagnostic.height, 8192)
        with Image.open(Path(self.context['output_dir']) / 'aligned.jpg') as aligned:
            self.assertEqual(aligned.size, (600, 410))

    def test_ocr_failure_rejects_value_with_reason(self):
        with patch('engine.recognize_number_block', side_effect=ValueError('Number block is ambiguous.')):
            result = run(self.data, self.settings, self.context)
        self.assertEqual(result['status'], 'unreadable')
        self.assertIsNone(result['readings'][0]['value'])
        self.assertIn('ambiguous', result['readings'][0]['reason'])

    def test_block_does_not_mix_with_comma_or_numeric_checks(self):
        self.settings['meters'][0]['layout'].append(',')
        with self.assertRaisesRegex(ReadingError, 'only pill'):resolve_layouts(self.settings)
        self.settings['meters'][0]['layout'] = ['digit-a']
        self.settings['meters'][0]['max_change'] = 10
        with patch('engine.recognize_number_block', return_value='00123456'):
            result = run(self.data, self.settings, self.context)
        self.assertEqual(result['status'], 'unreadable')
        self.assertIn('text', result['readings'][0]['reason'])


if __name__ == '__main__':unittest.main()
