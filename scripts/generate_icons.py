import os
from PIL import Image, ImageDraw

def create_transithear_icon(size, is_maskable=False):
    # Create image with deep navy background
    img = Image.new("RGBA", (size, size), (24, 35, 60, 255))
    draw = ImageDraw.Draw(img)

    # If maskable, safe zone is inner 80%
    padding = size * 0.18 if is_maskable else size * 0.12
    inner_size = size - 2 * padding

    # Draw rounded background badge with subtle gradient effect
    badge_margin = size * 0.06 if not is_maskable else size * 0.1
    draw.rounded_rectangle(
        [badge_margin, badge_margin, size - badge_margin, size - badge_margin],
        radius=int(size * 0.22),
        fill=(28, 43, 75, 255),
        outline=(56, 189, 248, 120),
        width=max(2, int(size * 0.02))
    )

    # Train Front Body
    cx = size / 2
    cy = size / 2 + size * 0.02
    tw = size * 0.38
    th = size * 0.44

    train_box = [cx - tw/2, cy - th/2, cx + tw/2, cy + th/2]
    # Train silhouette rounded rectangle
    draw.rounded_rectangle(train_box, radius=int(size * 0.07), fill=(241, 245, 249, 255))

    # Windshield / Screen (Teal / Signal Cyan)
    ww = tw * 0.78
    wh = th * 0.36
    wx = cx - ww/2
    wy = cy - th/2 + th * 0.1
    draw.rounded_rectangle([wx, wy, wx + ww, wy + wh], radius=int(size * 0.04), fill=(14, 165, 233, 255))

    # Headlights
    hl_y = cy + th * 0.24
    hl_r = max(2, int(size * 0.035))
    draw.ellipse([cx - tw * 0.3 - hl_r, hl_y - hl_r, cx - tw * 0.3 + hl_r, hl_y + hl_r], fill=(250, 204, 21, 255))
    draw.ellipse([cx + tw * 0.3 - hl_r, hl_y - hl_r, cx + tw * 0.3 + hl_r, hl_y + hl_r], fill=(250, 204, 21, 255))

    # Central Accessibility / Audio Wave Arc above train
    wave_cy = cy - th/2 - size * 0.08
    r1 = size * 0.12
    draw.arc([cx - r1, wave_cy - r1, cx + r1, wave_cy + r1], start=210, end=330, fill=(56, 189, 248, 255), width=max(2, int(size * 0.025)))
    r2 = size * 0.18
    draw.arc([cx - r2, wave_cy - r2, cx + r2, wave_cy + r2], start=220, end=320, fill=(20, 184, 166, 255), width=max(2, int(size * 0.025)))

    # Tracks / Rail indicator below train
    rw = tw * 1.15
    ry = cy + th/2 + size * 0.04
    draw.line([cx - rw/2, ry, cx + rw/2, ry], fill=(148, 163, 184, 255), width=max(2, int(size * 0.022)))

    return img

def main():
    icons_dir = os.path.join(os.path.dirname(__file__), "..", "public", "icons")
    os.makedirs(icons_dir, exist_ok=True)

    sizes = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-192.png", 192, True),
        ("icon-maskable-512.png", 512, True),
        ("apple-touch-icon.png", 180, False),
    ]

    for filename, size, maskable in sizes:
        path = os.path.join(icons_dir, filename)
        icon = create_transithear_icon(size, maskable)
        icon.save(path, "PNG")
        print(f"Generated {path} ({size}x{size})")

if __name__ == "__main__":
    main()
