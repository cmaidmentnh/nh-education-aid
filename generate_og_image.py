#!/usr/bin/env python3
"""Generate OG image for NH Education Funding Facts."""

from PIL import Image, ImageDraw, ImageFont
import os

WIDTH, HEIGHT = 1200, 630
basedir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(basedir, 'static', 'img', 'og-default.png')

# Fonts - Avenir Next for a clean, modern look
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
try:
    font_heavy_xl = ImageFont.truetype(AVENIR, 58, index=8)   # Heavy
    font_bold_lg = ImageFont.truetype(AVENIR, 40, index=0)    # Bold
    font_medium = ImageFont.truetype(AVENIR, 26, index=5)     # Medium
    font_bold_stat = ImageFont.truetype(AVENIR, 38, index=0)  # Bold
    font_demi_label = ImageFont.truetype(AVENIR, 16, index=2) # Demi Bold
    font_regular_sm = ImageFont.truetype(AVENIR, 20, index=7) # Regular
except Exception:
    font_heavy_xl = ImageFont.load_default()
    font_bold_lg = font_heavy_xl
    font_medium = font_heavy_xl
    font_bold_stat = font_heavy_xl
    font_demi_label = font_heavy_xl
    font_regular_sm = font_heavy_xl

# Create image
img = Image.new('RGB', (WIDTH, HEIGHT))
draw = ImageDraw.Draw(img)

# Gradient background - deep navy to slightly lighter
for y in range(HEIGHT):
    t = y / HEIGHT
    r = int(20 + t * 12)
    g = int(32 + t * 14)
    b = int(62 + t * 35)
    draw.line([(0, y), (WIDTH, y)], fill=(r, g, min(b, 255)))

# Top red accent bar
draw.rectangle([(0, 0), (WIDTH, 5)], fill=(232, 27, 35))

# Subtle diagonal accent line (decorative)
for i in range(3):
    offset = 40 + i * 3
    draw.line([(WIDTH - 300, 0), (WIDTH, offset)], fill=(232, 27, 35, 60), width=1)

# Title
title = "NH Education Funding Facts"
bbox = draw.textbbox((0, 0), title, font=font_heavy_xl)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 55), title, fill=(255, 255, 255), font=font_heavy_xl)

# Subtitle with growth stat
subtitle = "State Education Aid Has Grown 54%"
bbox = draw.textbbox((0, 0), subtitle, font=font_bold_lg)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 132), subtitle, fill=(255, 75, 82), font=font_bold_lg)

# Description
desc = "FY2004 - FY2027  |  Look up your town's funding history"
bbox = draw.textbbox((0, 0), desc, font=font_medium)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 192), desc, fill=(160, 172, 200), font=font_medium)

# Thin separator line
draw.rectangle([(150, 240), (WIDTH - 150, 241)], fill=(50, 65, 100))

# Stat boxes - 4 cards
stats = [
    ("$1.06 Billion", "Total State Aid (FY2027)"),
    ("$4,350", "Base Cost Per Pupil"),
    ("148,918", "Students (ADM)"),
    ("$7,133", "Aid Per Pupil"),
]

box_width = 250
box_height = 120
gap = 18
total_width = len(stats) * box_width + (len(stats) - 1) * gap
start_x = (WIDTH - total_width) / 2
start_y = 268

for i, (value, label) in enumerate(stats):
    x = start_x + i * (box_width + gap)

    # Card background with subtle border
    draw.rounded_rectangle(
        [(x, start_y), (x + box_width, start_y + box_height)],
        radius=10,
        fill=(30, 45, 78),
        outline=(55, 72, 110),
        width=1
    )

    # Value - centered
    bbox = draw.textbbox((0, 0), value, font=font_bold_stat)
    vw = bbox[2] - bbox[0]
    draw.text((x + (box_width - vw) / 2, start_y + 20), value, fill=(255, 75, 82), font=font_bold_stat)

    # Label - centered, wraps if needed
    bbox = draw.textbbox((0, 0), label, font=font_demi_label)
    lw = bbox[2] - bbox[0]
    draw.text((x + (box_width - lw) / 2, start_y + 78), label, fill=(140, 155, 185), font=font_demi_label)

# Bottom separator
draw.rectangle([(150, 420), (WIDTH - 150, 421)], fill=(50, 65, 100))

# Red accent bar near bottom
draw.rectangle([(80, 440), (WIDTH - 80, 443)], fill=(232, 27, 35))

# Domain
domain = "educationaid.nhhouse.gop"
bbox = draw.textbbox((0, 0), domain, font=font_medium)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 468), domain, fill=(200, 210, 230), font=font_medium)

# Attribution
attr = "Data from the NH Department of Education  |  Updated Annually"
bbox = draw.textbbox((0, 0), attr, font=font_regular_sm)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 520), attr, fill=(90, 105, 135), font=font_regular_sm)

# Bottom red accent
draw.rectangle([(0, HEIGHT - 5), (WIDTH, HEIGHT)], fill=(232, 27, 35))

# Paid for disclaimer
disclaimer = "Paid for by Committee to Elect House Republicans"
bbox = draw.textbbox((0, 0), disclaimer, font=font_demi_label)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 560), disclaimer, fill=(70, 85, 115), font=font_demi_label)

img.save(output_path, 'PNG', quality=95)
print(f"OG image saved to {output_path}")
print(f"Size: {os.path.getsize(output_path):,} bytes")
