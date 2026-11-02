"""按 device/ling-dictate.lua 的绘制参数复刻 240×240 设备界面，用来检查排版。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W = H = 240
BG = (0x0D, 0x14, 0x17)
CARD = (0x1B, 0x2A, 0x30)
LINE = (0x1E, 0x2A, 0x2E)
TITLE = (0xEA, 0xF3, 0xEF)
SUB = (0x8F, 0xA3, 0xA0)
ACCENT = (0x4E, 0xE1, 0xA0)

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"


def font(size: int = 16) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def text_center(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int, fill) -> None:
    f = font()
    w = draw.textlength(text, font=f)
    draw.text((x + (width - w) / 2, y), text, font=f, fill=fill)


def render(status: str, level: float, body: str, color=ACCENT) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")

    # 标题 + 状态胶囊
    d.text((14, 10), "小聆听写", font=font(), fill=TITLE)
    d.rounded_rectangle((148, 7, 228, 33), radius=13, fill=CARD)
    text_center(d, status, 148, 12, 80, color)

    # 麦克风
    d.ellipse((120 - 40, 90 - 40, 120 + 40, 90 + 40), outline=LINE, width=2)
    if level > 0.02:
        alpha = int(60 + level * 195)
        d.ellipse((120 - 40, 90 - 40, 120 + 40, 90 + 40), outline=color + (alpha,), width=4)
    d.ellipse((120 - 30, 90 - 30, 120 + 30, 90 + 30), fill=(0x14, 0x23, 0x2A))
    d.rounded_rectangle((112, 72, 128, 102), radius=8, fill=color)
    d.arc((120 - 19, 90 - 19, 120 + 19, 90 + 19), start=0, end=180, fill=color, width=3)
    d.line((120, 109, 120, 117), fill=color, width=3)

    # 最近一句 / 提示
    if body:
        lines = body.split("\n")
        for i, line in enumerate(lines):
            text_center(d, line, 12, 142 + i * 22, 216, TITLE)
    else:
        text_center(d, "对着板子说话", 12, 150, 216, SUB)
        text_center(d, "文字会落到光标处", 12, 172, 216, SUB)

    # 底部
    d.line((14, 206, 226, 206), fill=LINE, width=1)
    text_center(d, "功能键开关　长按3秒退出", 12, 214, 216, SUB)
    return img


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "docs"
    out.mkdir(exist_ok=True)

    cases = [
        ("听写中", 0.72, "明天下午2点开会，请带上电脑。", ACCENT),
        ("待命", 0.0, "", SUB),
        ("识别中", 0.35, "把这句话打到光标处，然后按回车。", (0xF0, 0xB3, 0x5C)),
    ]
    tiles = [render(*case) for case in cases]
    sheet = Image.new("RGB", (W * len(tiles) + 16 * (len(tiles) - 1), H), (10, 12, 14))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (i * (W + 16), 0))
    path = out / "device-ui.png"
    sheet.save(path)
    print("saved", path)


if __name__ == "__main__":
    main()
