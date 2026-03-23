"""Generate simple extension icons as PNG files using PIL."""
from PIL import Image, ImageDraw

SIZES = [16, 48, 128]
BG_COLOR = (99, 102, 241)  # Indigo-500
FG_COLOR = (255, 255, 255)

for size in SIZES:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circle background
    margin = size // 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=BG_COLOR)

    # Microphone shape (simplified)
    cx, cy = size // 2, size // 2
    r = size // 6

    # Mic body
    draw.rounded_rectangle(
        [cx - r, cy - r * 2, cx + r, cy + r],
        radius=r,
        fill=FG_COLOR,
    )

    # Stand
    line_w = max(1, size // 16)
    draw.line([cx, cy + r, cx, cy + r + size // 8], fill=FG_COLOR, width=line_w)
    draw.line(
        [cx - size // 8, cy + r + size // 8, cx + size // 8, cy + r + size // 8],
        fill=FG_COLOR,
        width=line_w,
    )

    img.save(f"icon{size}.png")
    print(f"Created icon{size}.png")
