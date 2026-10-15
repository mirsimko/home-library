"""Generated EAN-13 images with wide bars and quiet zones for decoder tests."""
from PIL import Image, ImageDraw

L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
G = ("0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111")
R = ("1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100")
PARITY = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")


def ean13(text):
    """Render the supplied digits as bars; leave a deliberately wrong check digit untouched."""
    left = "".join((L if kind == "L" else G)[int(digit)]
                   for kind, digit in zip(PARITY[int(text[0])], text[1:7]))
    bars = "101" + left + "01010" + "".join(R[int(digit)] for digit in text[7:]) + "101"
    image = Image.new("RGB", ((95 + 24) * 4, 280), "white")
    draw = ImageDraw.Draw(image)
    for i, bar in enumerate(bars):
        if bar == "1":
            draw.rectangle(((i + 12) * 4, 20, (i + 13) * 4 - 1, 259), fill="black")
    return image
