import random


_generated_colors = set()


def generate_unique_hex_color():
    def random_color():
        return "#{:06x}".format(random.randint(0, 0xFFFFFF))

    def luminance(hex_color):
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    while True:
        color = random_color()
        if color not in _generated_colors:
            lum = luminance(color)
            if 50 < lum < 200:  # Ensuring the color is neither too dark nor too light
                _generated_colors.add(color)
                return color
