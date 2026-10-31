"""Local printed-number OCR adapted from our original watermeter App.

Two threshold variants must agree. No fixed image coordinates or private meter
identity are embedded here. Results remain strings, including leading zeroes.
"""
from io import BytesIO
import os
import re
import subprocess
import time

import cv2
import numpy as np
from PIL import Image, ImageOps


def recognize(image, expected_length=None, expected_value=None, *, deadline=None, trace=None):
    if expected_length is not None and (type(expected_length) is not int or not 1 <= expected_length <= 32):
        raise ValueError('Number block length must be between 1 and 32 digits.')
    if expected_value is not None and (not isinstance(expected_value, str) or not re.fullmatch(r'[0-9]{1,32}', expected_value)):
        raise ValueError('Number block comparison must contain 1 to 32 digits.')
    if expected_value is not None and expected_length is not None and len(expected_value) != expected_length:
        raise ValueError('Number block comparison and expected length do not match.')
    deadline = deadline if deadline is not None else time.monotonic() + 16
    # Preserve the old sixfold enlargement, bounded for arbitrary editor crops.
    scale = min(6, 2048 / image.width, 512 / image.height)
    target_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    crop = image.convert('L')
    crop.thumbnail((1024, 256), Image.Resampling.LANCZOS)
    # Estimate the light paper/background behind dark strokes before thresholding.
    # Closing fills digit strokes while retaining gradual shadows and illumination.
    pixels = np.asarray(crop)
    kernel_size = max(3, round(crop.height * 0.45) | 1)
    background = cv2.morphologyEx(pixels, cv2.MORPH_CLOSE,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)))
    normalized = cv2.divide(pixels, np.maximum(background, 1), scale=255)
    threshold, _ = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    crop = Image.fromarray(normalized).resize(target_size, Image.Resampling.LANCZOS)
    if trace:trace('Illumination correction',crop,'Background normalization; image-derived threshold')
    results = []
    # Both nearby, image-derived thresholds must still produce the same number.
    for threshold in (max(1, threshold - 5), min(254, threshold + 5)):
        timeout = min(8, deadline - time.monotonic())
        if timeout <= 0:
            raise ValueError('Number block recognition timed out.')
        variant = crop.point(lambda p: 255 if p > threshold else 0)
        data = BytesIO()
        ImageOps.expand(variant, border=30, fill=255).save(data, format='PNG')
        try:
            result = subprocess.run(
                ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '7', '-c', 'tessedit_char_whitelist=0123456789'],
                input=data.getvalue(), capture_output=True, timeout=timeout, check=True,
                env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
            )
        except FileNotFoundError:
            raise ValueError('Number block recognition requires Tesseract in the Studio runtime. Rebuild or update Studio.') from None
        except subprocess.TimeoutExpired:
            raise ValueError('Number block recognition timed out.') from None
        except (subprocess.CalledProcessError, OSError):
            raise ValueError('Number block OCR failed.') from None
        text = ''.join(result.stdout.decode('utf-8', errors='replace').split())
        if trace:trace('OCR threshold',variant,f'Threshold={threshold:.1f} | OCR={text or "unreadable"}')
        if not re.fullmatch(r'[0-9]{1,32}', text):
            raise ValueError('Number block could not be read as 1 to 32 digits.')
        results.append(text)
    if results[0] != results[1]:
        raise ValueError('Number block is ambiguous: the two image variants disagree.')
    text = results[0]
    if expected_length is not None and len(text) != expected_length:
        raise ValueError('Number block does not match the expected length.')
    if expected_value is not None and text != expected_value:
        raise ValueError('Number block does not match the expected value.')
    return text
