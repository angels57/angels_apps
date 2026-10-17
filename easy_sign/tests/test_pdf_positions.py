"""The flattened values must land where the fields were placed (±2 pt).

Positions are read back from the final PDF (PyPDF2 text visitor, user space)
and converted to the *displayed* page with the PDF rule for ``/Rotate``
(clockwise), independently of the overlay code.
"""
import io

from reportlab.lib.pagesizes import A4, landscape

from odoo.tests import tagged
from odoo.tools import pdf as odoo_pdf
from odoo.tools.pdf import PdfReader

from .common import EasySignCase, make_pdf, make_png
from ..utils.compat import binary_bytes

TOLERANCE = 2.0  # points
# PyPDF2 2.x reports the text matrix one leading (1.2 x size, reportlab's
# default) below the real baseline; pypdf does not.
LEADING_FIX = 1.2 if getattr(odoo_pdf, "SUBMOD", "") == "._pypdf2_2" else 0.0


def displayed_point(x, y, llx, lly, width, height, rotation):
    """User-space point -> (X, Y) on the displayed page, origin top-left."""
    x, y = x - llx, y - lly
    if rotation == 90:
        return y, x
    if rotation == 180:
        return width - x, y
    if rotation == 270:
        return height - y, width - x
    return x, height - y


@tagged("post_install", "-at_install")
class TestPdfPositions(EasySignCase):

    def _signed_text_positions(self, request):
        reader = PdfReader(io.BytesIO(binary_bytes(request.signed_document)))
        found = {}
        for page in reader.pages:
            box = page.mediabox
            llx, lly, width, height = float(box.left), float(box.bottom), float(box.width), float(box.height)
            rotation = int(page.get("/Rotate", 0) or 0) % 360

            def visitor(text, cm, tm, font_dict, font_size, _geo=(llx, lly, width, height, rotation)):
                text = (text or "").strip()
                if text.startswith("Easy Sign ·"):
                    text = "FOOTER%d" % len([k for k in found if k.startswith("FOOTER")])
                if text.startswith(("VAL", "FOOTER")):
                    tx, ty = tm[4], tm[5] + LEADING_FIX * font_size
                    ux = cm[0] * tx + cm[2] * ty + cm[4]
                    uy = cm[1] * tx + cm[3] * ty + cm[5]
                    found[text] = displayed_point(ux, uy, *_geo) + (_geo,)

            page.extract_text(visitor_text=visitor)
        return found

    def test_values_at_field_position(self):
        cases = [
            ("VALPORTRAIT", None, 0),
            ("VALLANDSCAPE", landscape(A4), 0),
            ("VALROT90", None, 90),
            ("VALROT180", None, 180),
            ("VALROT270", None, 270),
        ]
        request = self.env["sign.request"].create({})
        signer = self.env["sign.request.item"].create({
            "request_id": request.id, "signer_name": "A", "signer_email": "a@example.test",
        })
        fields = {}
        for index, (value, size, rotation) in enumerate(cases):
            doc = self.env["sign.document"].create({
                "request_id": request.id, "sequence": index, "name": f"{value}.pdf",
                "file": make_pdf(1, rotate=rotation, pagesize=size),
            })
            fields[value] = self.add_field(
                request, doc, signer, "text", pos_x=0.2 + index * 0.05, pos_y=0.3, width=0.4, height=0.04,
            )
        request.action_send()
        signer._sign(make_png(), "draw", values={f.id: v for v, f in fields.items()})
        self.assertEqual(request.state, "signed")

        positions = self._signed_text_positions(request)
        for value, field in fields.items():
            self.assertIn(value, positions, f"{value} not found in the signed PDF")
            x, y, (_llx, _lly, width, height, rotation) = positions[value]
            dw, dh = (height, width) if rotation in (90, 270) else (width, height)
            left, top = field.pos_x * dw, field.pos_y * dh
            bottom = top + field.height * dh
            # Left-aligned text starts at the left edge of the field (1 pt padding).
            self.assertAlmostEqual(x, left + 1, delta=TOLERANCE, msg=f"{value}: x={x:.1f} expected {left + 1:.1f}")
            # The baseline is inside the field box.
            self.assertGreaterEqual(y, top - TOLERANCE, f"{value}: baseline above the field")
            self.assertLessEqual(y, bottom + TOLERANCE, f"{value}: baseline below the field")
        # Calibration: the footer is drawn at 10 pt from the bottom of every
        # displayed page, which validates the coordinate reading itself.
        footers = [v for k, v in positions.items() if k.startswith("FOOTER")]
        self.assertEqual(len(footers), len(cases))
        for _x, y, (_llx, _lly, width, height, rotation) in footers:
            dh = width if rotation in (90, 270) else height
            self.assertAlmostEqual(y, dh - 10, delta=0.5)
