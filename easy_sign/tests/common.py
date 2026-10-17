import io

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from odoo.tests.common import TransactionCase
from odoo.tools.pdf import NameObject, NumberObject, PdfReader, PdfWriter

from ..utils.binary import binary_value


def make_pdf(pages=2, rotate=0, pagesize=None):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=pagesize) if pagesize else canvas.Canvas(buffer)
    for number in range(pages):
        pdf.drawString(72, 750, f"Page {number + 1}")
        pdf.showPage()
    pdf.save()
    data = buffer.getvalue()
    if rotate:
        reader = PdfReader(io.BytesIO(data))
        writer = PdfWriter()
        for page in reader.pages:
            page[NameObject("/Rotate")] = NumberObject(rotate)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        data = out.getvalue()
    return binary_value(data)


def make_png():
    image = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(image).line((10, 80, 290, 20), fill="black", width=4)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class EasySignCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.email = "owner@example.test"
        cls.partner_a = cls.env["res.partner"].create({"name": "Ana", "email": "ana@example.test", "city": "Cali"})
        cls.partner_b = cls.env["res.partner"].create({"name": "Beto", "email": "beto@example.test"})

    def make_request(self, signers=2, order=False, **vals):
        request = self.env["sign.request"].create(dict({"signing_order": order}, **vals))
        doc = self.env["sign.document"].create({"request_id": request.id, "name": "doc.pdf", "file": make_pdf()})
        partners = (self.partner_a | self.partner_b)[:signers]
        for seq, partner in enumerate(partners, start=1):
            self.env["sign.request.item"].create({
                "request_id": request.id, "sequence": seq * 10, "partner_id": partner.id,
                "signer_name": partner.name, "signer_email": partner.email,
            })
        return request, doc

    def add_field(self, request, doc, signer, ftype="signature", **vals):
        return self.env["sign.item"].create(dict({
            "request_id": request.id, "document_id": doc.id, "request_item_id": signer.id,
            "type": ftype, "page": 1, "pos_x": 0.1, "pos_y": 0.5, "width": 0.3, "height": 0.08,
        }, **vals))
