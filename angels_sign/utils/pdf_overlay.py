"""Draw field values on top of PDF pages with reportlab.

Positions come from the editor as fractions (0-1) of the page *as displayed*
(pdf.js applies ``/Rotate``), measured from the top-left corner. The overlay is
drawn in that displayed space and transformed back to the page's user space.
"""
import io
import os

from PIL import Image
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

FONT = "Helvetica"
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
if os.path.exists(_DEJAVU):
    try:
        pdfmetrics.registerFont(TTFont("EasySignSans", _DEJAVU))
        FONT = "EasySignSans"
    except Exception:  # noqa: BLE001 - keep Helvetica
        pass

FRAME_COLOR = (0.15, 0.39, 0.92)
TEXT_COLOR = (0.08, 0.1, 0.2)


def page_geometry(page):
    box = page.mediabox
    llx, lly = float(box.left), float(box.bottom)
    width, height = float(box.width), float(box.height)
    rotation = int(page.get("/Rotate", 0) or 0) % 360
    return llx, lly, width, height, rotation


class PageOverlay:
    def __init__(self, page):
        self.llx, self.lly, self.w, self.h, self.rotation = page_geometry(page)
        self.buffer = io.BytesIO()
        self.canvas = rl_canvas.Canvas(self.buffer, pagesize=(self.llx + self.w, self.lly + self.h))
        self.dw, self.dh = (self.h, self.w) if self.rotation in (90, 270) else (self.w, self.h)
        c = self.canvas
        c.translate(self.llx, self.lly)
        if self.rotation == 90:
            c.translate(self.w, 0)
            c.rotate(90)
        elif self.rotation == 180:
            c.translate(self.w, self.h)
            c.rotate(180)
        elif self.rotation == 270:
            c.translate(0, self.h)
            c.rotate(270)
        self.empty = True

    def box(self, x, y, w, h):
        """Relative top-left box -> (X, Y, W, H) in displayed points, bottom-left origin."""
        return x * self.dw, (1 - y - h) * self.dh, w * self.dw, h * self.dh

    def text(self, value, box, align="left", multiline=False):
        if not value:
            return
        self.empty = False
        x, y, w, h = box
        c = self.canvas
        c.setFillColorRGB(*TEXT_COLOR)
        if multiline:
            size = min(10.0, max(6.0, h / 4))
            lines = simpleSplit(value, FONT, size, w)
            top = y + h - size
            for line in lines:
                if top < y - 1:
                    break
                self._draw_line(line, x, top, w, size, align)
                top -= size * 1.2
            return
        size = min(11.0, max(6.0, h * 0.62))
        while size > 5 and pdfmetrics.stringWidth(value, FONT, size) > w:
            size -= 0.5
        self._draw_line(value, x, y + (h - size) / 2 + size * 0.15, w, size, align)

    def _draw_line(self, line, x, y, w, size, align):
        c = self.canvas
        c.setFont(FONT, size)
        if align == "center":
            c.drawCentredString(x + w / 2, y, line)
        elif align == "right":
            c.drawRightString(x + w, y, line)
        else:
            c.drawString(x + 1, y, line)

    def image(self, png_bytes, box, frame_text=None):
        if not png_bytes:
            return
        self.empty = False
        x, y, w, h = box
        img = Image.open(io.BytesIO(png_bytes))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        c = self.canvas
        pad = 2 if frame_text else 0
        c.drawImage(ImageReader(img), x + pad, y + pad, width=w - 2 * pad, height=h - 2 * pad,
                    preserveAspectRatio=True, anchor="c", mask="auto")
        if frame_text:
            c.setStrokeColorRGB(*FRAME_COLOR)
            c.setLineWidth(0.6)
            c.roundRect(x, y, w, h, 3, stroke=1, fill=0)
            c.setFillColorRGB(*FRAME_COLOR)
            c.setFont(FONT, 4.5)
            c.drawString(x + 2, y + h - 5.5, frame_text)

    def check(self, box, checked):
        self.empty = False
        x, y, w, h = box
        side = min(w, h)
        c = self.canvas
        c.setStrokeColorRGB(*TEXT_COLOR)
        c.setLineWidth(0.8)
        c.rect(x, y + (h - side) / 2, side, side)
        if checked:
            c.line(x + side * 0.2, y + (h - side) / 2 + side * 0.5, x + side * 0.42, y + (h - side) / 2 + side * 0.25)
            c.line(x + side * 0.42, y + (h - side) / 2 + side * 0.25, x + side * 0.82, y + (h - side) / 2 + side * 0.8)

    def strike(self, box):
        self.empty = False
        x, y, w, h = box
        c = self.canvas
        c.setStrokeColorRGB(0.8, 0.1, 0.1)
        c.setLineWidth(1.2)
        c.line(x, y + h / 2, x + w, y + h / 2)

    def radio(self, options, selected, box):
        if not options:
            return
        self.empty = False
        x, y, w, h = box
        row = h / len(options)
        size = min(10.0, max(5.0, row * 0.6))
        c = self.canvas
        for idx, option in enumerate(options):
            cy = y + h - row * (idx + 0.5)
            c.setStrokeColorRGB(*TEXT_COLOR)
            c.circle(x + size / 2, cy, size / 2.4, stroke=1, fill=0)
            if option == selected:
                c.setFillColorRGB(*TEXT_COLOR)
                c.circle(x + size / 2, cy, size / 4.5, stroke=0, fill=1)
            c.setFillColorRGB(*TEXT_COLOR)
            c.setFont(FONT, size)
            c.drawString(x + size * 1.3, cy - size * 0.35, option)

    def footer(self, text):
        self.empty = False
        c = self.canvas
        c.setFillColorRGB(0.45, 0.45, 0.5)
        c.setFont(FONT, 6.5)
        c.drawCentredString(self.dw / 2, 10, text)

    def caption(self, text, x, y, size=6.5):
        c = self.canvas
        c.setFillColorRGB(0.4, 0.4, 0.45)
        c.setFont(FONT, size)
        c.drawString(x, y, text)

    def render(self):
        self.canvas.showPage()
        self.canvas.save()
        return self.buffer.getvalue()
