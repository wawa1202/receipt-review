"""自制演示收据，不包含个人信息，也不代表公开数据集成绩。"""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEMO_FIELDS = {'company': 'DEMO MART', 'address': '12 JALAN MAJU', 'date': '2024-05-27', 'total': '12.00'}


def receipt_image():
    image = Image.new('RGB', (900, 1080), 'white')
    draw = ImageDraw.Draw(image)
    fonts = [Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    path = next((path for path in fonts if path.exists()), None)
    font = ImageFont.truetype(str(path), 38) if path else ImageFont.load_default(size=38)
    lines = ['DEMO MART', '12 JALAN MAJU', 'Date: 27/05/2024', 'Receipt: DEMO-001',
             'Coffee                 12.00', 'SUBTOTAL             12.00',
             'TOTAL                  12.00', 'CASH                   20.00',
             'CHANGE                  8.00', 'SYNTHETIC DEMO - NOT A REAL RECEIPT']
    for i, text in enumerate(lines):
        draw.text((55, 50 + 94*i), text, font=font, fill='black')
    stream = BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()
