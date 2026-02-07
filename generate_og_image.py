#!/usr/bin/env python3
"""Generate OG image for NH Education Funding Facts."""

from PIL import Image, ImageDraw, ImageFont
import os

WIDTH, HEIGHT = 1200, 630
basedir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(basedir, 'static', 'img', 'og-default.png')

# Create image with gradient-like navy background
img = Image.new('RGB', (WIDTH, HEIGHT))
draw = ImageDraw.Draw(img)

# Create gradient background (navy to darker navy)
for y in range(HEIGHT):
    r = int(27 - (y / HEIGHT) * 10)
    g = int(42 - (y / HEIGHT) * 15)
    b = int(74 + (y / HEIGHT) * 30)
    draw.line([(0, y), (WIDTH, y)], fill=(max(r, 0), max(g, 0), min(b, 255)))

# Draw decorative red accent bar at top
draw.rectangle([(0, 0), (WIDTH, 6)], fill=(232, 27, 35))

# Draw decorative red accent bar at bottom
draw.rectangle([(0, HEIGHT - 6), (WIDTH, HEIGHT)], fill=(232, 27, 35))

# Try to use a nice font, fall back to default
try:
    font_bold_xl = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 56)
    font_bold_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
    font_regular = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    font_stat = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
    font_stat_label = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
except:
    font_bold_xl = ImageFont.load_default()
    font_bold_lg = font_bold_xl
    font_regular = font_bold_xl
    font_stat = font_bold_xl
    font_stat_label = font_bold_xl

# Title
title = "NH Education Funding Facts"
bbox = draw.textbbox((0, 0), title, font=font_bold_xl)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 60), title, fill=(255, 255, 255), font=font_bold_xl)

# Subtitle
subtitle = "State Education Aid Has Grown 54%"
bbox = draw.textbbox((0, 0), subtitle, font=font_bold_lg)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 140), subtitle, fill=(255, 75, 82), font=font_bold_lg)

# Description
desc = "From FY2004 to FY2027 - Look up your town's funding history"
bbox = draw.textbbox((0, 0), desc, font=font_regular)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 200), desc, fill=(180, 190, 210), font=font_regular)

# Stat boxes
stats = [
    ("$698M+", "Total State Aid"),
    ("$4,350", "Base Per-Pupil"),
    ("148,918", "Students"),
    ("$7,133", "Aid Per Pupil"),
]

box_width = 240
box_height = 140
total_width = len(stats) * box_width + (len(stats) - 1) * 20
start_x = (WIDTH - total_width) / 2
start_y = 290

for i, (value, label) in enumerate(stats):
    x = start_x + i * (box_width + 20)
    # Draw semi-transparent box
    draw.rounded_rectangle(
        [(x, start_y), (x + box_width, start_y + box_height)],
        radius=12,
        fill=(40, 55, 90),
        outline=(60, 80, 120),
        width=1
    )
    # Value
    bbox = draw.textbbox((0, 0), value, font=font_stat)
    vw = bbox[2] - bbox[0]
    draw.text((x + (box_width - vw) / 2, start_y + 25), value, fill=(255, 75, 82), font=font_stat)
    # Label
    bbox = draw.textbbox((0, 0), label, font=font_stat_label)
    lw = bbox[2] - bbox[0]
    draw.text((x + (box_width - lw) / 2, start_y + 95), label, fill=(160, 170, 190), font=font_stat_label)

# Red accent line
draw.rectangle([(100, 480), (WIDTH - 100, 482)], fill=(232, 27, 35))

# Bottom text
bottom = "educationaid.nhhouse.gop"
bbox = draw.textbbox((0, 0), bottom, font=font_regular)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 510), bottom, fill=(140, 150, 170), font=font_regular)

# Attribution
attr = "Data from NH Department of Education | FY2004-FY2027"
bbox = draw.textbbox((0, 0), attr, font=font_stat_label)
tw = bbox[2] - bbox[0]
draw.text(((WIDTH - tw) / 2, 560), attr, fill=(100, 110, 130), font=font_stat_label)

img.save(output_path, 'PNG', quality=95)
print(f"OG image saved to {output_path}")
print(f"Size: {os.path.getsize(output_path):,} bytes")
