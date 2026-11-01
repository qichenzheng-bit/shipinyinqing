"""Build the WeiGuang book/star Windows icon from the approved website mark.

Source design: graphite rounded square, muted-gold four-point light, three
open-book contours. No third-party font assets or external image downloads.
The icon uses Pillow so Linux/Windows CI can regenerate identical files.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = "#24272D"
PAPER = "#F9F9F6"
PAGE = "#C5C8CD"
GOLD = "#CEAB63"


def bezier(start, control1, control2, end, steps=48):
    points = []
    for i in range(steps + 1):
        t = i / steps
        q = 1 - t
        points.append((
            q**3 * start[0] + 3*q*q*t*control1[0] +
            3*q*t*t*control2[0] + t**3 * end[0],
            q**3 * start[1] + 3*q*q*t*control1[1] +
            3*q*t*t*control2[1] + t**3 * end[1],
        ))
    return points


def icon(size=512):
    sc = size / 512
    image = Image.new("RGBA", (size,size), (0,0,0,0))
    draw = ImageDraw.Draw(image)

    def scale(point):
        return tuple(round(value * sc) for value in point)

    def stroke(points, color, width):
        draw.line(
            [scale(point) for point in points], fill=color,
            width=round(width*sc), joint="curve",
        )

    draw.rounded_rectangle(
        scale((0,0,511,511)),radius=round(106*sc),fill=BACKGROUND,
    )
    for x,y,r in ((145,145,4),(362,147,4),(109,211,3),(400,211,3)):
        draw.ellipse(scale((x-r,y-r,x+r,y+r)),fill="#96969A")

    # Same central four-point light used above the original brand book.
    points=[]
    for i in range(32):
        angle=math.tau*i/32
        r=66/(1+3.9*abs(math.sin(2*angle)))
        points.append((256+math.sin(angle)*r,172-math.cos(angle)*r))
    draw.polygon([scale(p) for p in points],fill=GOLD)

    stroke(bezier((96,308),(155,280),(207,286),(256,326)),PAPER,17)
    stroke(bezier((256,326),(306,286),(360,280),(417,308)),PAPER,17)
    stroke(bezier((96,345),(162,323),(211,334),(256,367)),PAGE,11)
    stroke(bezier((256,367),(303,334),(352,323),(417,345)),PAGE,11)
    stroke(bezier((96,377),(162,358),(216,374),(256,396)),"#898F98",6)
    stroke(bezier((256,396),(296,374),(351,358),(417,377)),"#898F98",6)
    stroke(((256,326),(256,395)),PAPER,8)
    return image


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("desktop/build"))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    image=icon()
    image.save(args.output/"app.png")
    image.save(
        args.output/"app.ico",
        sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)],
    )
    assert (args.output/"app.ico").stat().st_size > 1000
    print("WINDOWS_APP_ICON_OK",args.output/"app.ico")


if __name__=="__main__":
    main()
