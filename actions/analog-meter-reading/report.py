"""Private, bounded image report of the actual preview processing steps."""
import math
import textwrap
from PIL import Image, ImageDraw, ImageFont


class Report:
    def __init__(self):
        self.cards = []

    def add(self, title, image=None, details=''):
        card = Image.new('RGB', (384, 300), '#ffffff')
        draw = ImageDraw.Draw(card)
        font = ImageFont.load_default(size=14)
        draw.text((12, 10), str(title)[:46], fill='#0277bd', font=font)
        if image is not None:
            thumb = image.convert('RGB')
            thumb.thumbnail((360, 170))
            card.paste(thumb, ((384-thumb.width)//2, 38))
        lines = textwrap.wrap(str(details), width=46)
        for index, line in enumerate(lines[:5]):
            draw.text((12, (216 if image is not None else 40)+index*16), line, fill='#263238', font=font)
        self.cards.append(card)

    def save(self, path, result):
        for reading in result['readings']:
            self.add('Value: '+reading['name'], details=f"{reading['status']} | value={reading['value']} {reading['unit']} | raw={reading.get('raw_value')} | {reading.get('reason') or 'Checks passed'} | confirmation={reading.get('confirmation', 'not requested')}")
        pages = math.ceil(len(self.cards)/72)
        for page in range(pages):
            cards = self.cards[page*72:(page+1)*72]
            height = 80 + math.ceil(len(cards)/3)*312
            canvas = Image.new('RGB', (1180, height), '#e9eef2')
            draw = ImageDraw.Draw(canvas)
            draw.text((16, 12), 'Analog Meter Reader - Recognition report', fill='#0277bd', font=ImageFont.load_default(size=24))
            draw.text((16, 46), f"Page {page+1}/{pages} | Result: {result['status']} | Processing order | Fit is not a probability", fill='#263238', font=ImageFont.load_default(size=15))
            for i, card in enumerate(cards):
                canvas.paste(card, (8+(i%3)*392, 80+(i//3)*312))
            canvas.save(path.with_name(f'{path.stem}-{page+1:02d}.jpg'), quality=88)
