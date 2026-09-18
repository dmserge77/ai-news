#!/usr/bin/env python3
"""Рисует og-image.png — картинку для карточки предпросмотра ссылки.

РУЧНОЙ СКРИПТ, В СБОРКУ НЕ ВХОДИТ.

Сборщик проекта живёт на одной стандартной библиотеке, а здесь нужен Pillow.
Запускать только вручную и только когда меняется название или подзаголовок:

    pip install Pillow
    python make_og_image.py

Готовый og-image.png лежит в корне проекта и в git. При сборке его копирует
в docs/ функция copy_static() — иначе он пропал бы вместе с docs/.

Почему картинка, а не скриншот страницы: пропорция скриншота 1.6:1, и
мессенджер обрезает его по центру — срезает ровно шапку с названием. Плюс
в кадре застывают счётчики и время сборки, а сайт пересобирается 6 раз в день.
Здесь нарисована чистая карточка без цифр и даты — она не устаревает.

Почему 1200x630: это 1.91:1, стандарт карточек. Telegram не принимает
тяжелее 5 МБ, мы держим далеко ниже.
"""

import os

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "og-image.png")

W, H = 1200, 630

# Формулировки обязаны совпадать с сайтом слово в слово. Расхождение ловит
# tests/test_render.py — на карточке и на страницах текст живёт отдельно
# и разъезжается молча.
TITLE = "Нейрорадар"
TAGLINE = "Что нового в ИИ — шесть раз в день"
ICON = "\U0001F4E1"  # 📡

# Цвета взяты с самого сайта (MAIN_CSS в news/render.py), чтобы карточка
# выглядела его продолжением, а не чужой картинкой.
BG = (245, 245, 247)          # --bg
TEXT2 = (110, 110, 115)       # --text2
GRAD_FROM = (0, 113, 227)     # --accent
GRAD_TO = (88, 86, 214)       # второй цвет градиента заголовка

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_EMOJI = r"C:\Windows\Fonts\seguiemj.ttf"


def main():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    font_title = ImageFont.truetype(FONT_BOLD, 108)
    font_tag = ImageFont.truetype(FONT_BOLD, 36)
    font_emoji = ImageFont.truetype(FONT_EMOJI, 96)

    # Эмодзи сверху. Только с embedded_color=True — без него выйдет чёрный силуэт.
    d.text((W / 2, 150), ICON, font=font_emoji, anchor="mm", embedded_color=True)

    # Заголовок градиентом: рисуем маску буквами, потом заливаем её градиентом.
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((W / 2, 320), TITLE, font=font_title, fill=255, anchor="mm")
    grad = Image.new("RGB", (W, H))
    gd = ImageDraw.Draw(grad)
    for x in range(W):
        t = x / (W - 1)
        gd.line([(x, 0), (x, H)], fill=(
            int(GRAD_FROM[0] + (GRAD_TO[0] - GRAD_FROM[0]) * t),
            int(GRAD_FROM[1] + (GRAD_TO[1] - GRAD_FROM[1]) * t),
            int(GRAD_FROM[2] + (GRAD_TO[2] - GRAD_FROM[2]) * t),
        ))
    im.paste(grad, (0, 0), mask)

    d.text((W / 2, 440), TAGLINE, font=font_tag, fill=TEXT2, anchor="mm")

    im.save(OUT_PATH, optimize=True)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"[OK] {OUT_PATH}")
    print(f"     {W}x{H}, {size_kb:.0f} КБ")


if __name__ == "__main__":
    main()
