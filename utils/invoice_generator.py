"""
utils/invoice_generator.py - invoice text file (file handling) and PDF.

build_invoice_text() produces the same 66-column layout as show_invoice() in
the project report. save_invoice_text() writes it to exports/invoice_N.txt
using Python text-file handling. build_invoice_pdf() makes a PDF with
reportlab.
"""
import io
import os

from utils.gst import split_gst

WIDTH = 66


def _clip(text, size):
    """Cut a text to a maximum length (used for fixed-width columns)."""
    text = "" if text is None else str(text)
    return text[:size]


def build_invoice_text(invoice, items, shop):
    """Return the invoice as a plain-text string."""
    cgst, sgst = split_gst(invoice["total_gst"])
    shop_line = shop["name"]
    if shop.get("address"):
        shop_line += ", " + shop["address"]

    lines = []
    lines.append("=" * WIDTH)
    lines.append(_clip(shop_line, WIDTH).center(WIDTH))
    if shop.get("gstin"):
        lines.append(("GSTIN: " + shop["gstin"]).center(WIDTH))
    lines.append("TAX INVOICE".center(WIDTH))
    lines.append("=" * WIDTH)
    lines.append("Invoice No : %-10s            Date : %s"
                 % (invoice["inv_no"], invoice["inv_date"]))
    lines.append("Customer   : %s" % invoice["customer_name"])
    if invoice.get("phone"):
        lines.append("Phone      : %s" % invoice["phone"])
    if invoice.get("gstin"):
        lines.append("GSTIN      : %s" % invoice["gstin"])
    lines.append("-" * WIDTH)
    lines.append("%-20s %4s %8s %5s %10s %9s"
                 % ("Item", "Qty", "Rate", "GST%", "Taxable", "GST"))
    lines.append("-" * WIDTH)
    for it in items:
        lines.append("%-20s %4d %8.2f %5d %10.2f %9.2f"
                     % (_clip(it["name"], 20), it["qty"], it["rate"],
                        it["gst_rate"], it["taxable"], it["gst_amt"]))
    lines.append("-" * WIDTH)
    lines.append("%46s %10.2f" % ("Sub-total (taxable) :", invoice["subtotal"]))
    lines.append("%46s %10.2f" % ("CGST :", cgst))
    lines.append("%46s %10.2f" % ("SGST :", sgst))
    lines.append("%46s %10.2f" % ("GRAND TOTAL (Rs.) :", invoice["grand_total"]))
    lines.append("=" * WIDTH)
    return "\n".join(lines)


def save_invoice_text(inv_no, text, export_dir):
    """Save the invoice text to exports/invoice_<number>.txt; return the path."""
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, "invoice_%d.txt" % int(inv_no))
    with open(path, "w", encoding="utf-8") as f:       # text-file handling
        f.write(text)
    return path


def build_invoice_pdf(invoice, items, shop):
    """Return the invoice as PDF bytes (A4)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    navy = colors.HexColor("#0B2A5B")
    soft = colors.HexColor("#EEF3FB")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], textColor=navy, fontSize=18)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, leading=12)
    center = ParagraphStyle("c", parent=small, alignment=1)

    cgst, sgst = split_gst(invoice["total_gst"])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm,
                            rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm,
                            title="Invoice %s" % invoice["inv_no"])
    story = [Paragraph(_esc(shop["name"]), title)]
    sub = shop.get("address", "")
    if shop.get("phone"):
        sub += "  |  Phone: " + shop["phone"]
    if shop.get("gstin"):
        sub += "  |  GSTIN: " + shop["gstin"]
    if sub.strip():
        story.append(Paragraph(_esc(sub), center))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>TAX INVOICE</b>", center))
    story.append(Spacer(1, 4 * mm))

    bill = ["<b>Bill to:</b> " + _esc(invoice["customer_name"])]
    if invoice.get("phone"):
        bill.append("Phone: " + _esc(invoice["phone"]))
    if invoice.get("gstin"):
        bill.append("GSTIN: " + _esc(invoice["gstin"]))
    meta = ["<b>Invoice No:</b> %s" % invoice["inv_no"],
            "<b>Date:</b> %s" % invoice["inv_date"]]
    head = Table([[Paragraph("<br/>".join(bill), small),
                   Paragraph("<br/>".join(meta), small)]],
                 colWidths=[110 * mm, 70 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(head)
    story.append(Spacer(1, 4 * mm))

    data = [["#", "Item", "Qty", "Rate", "GST %", "Taxable", "GST"]]
    for number, it in enumerate(items, start=1):
        data.append([str(number), Paragraph(_esc(it["name"]), small),
                     str(it["qty"]), "%.2f" % it["rate"], str(it["gst_rate"]),
                     "%.2f" % it["taxable"], "%.2f" % it["gst_amt"]])
    table = Table(data, colWidths=[9 * mm, 68 * mm, 14 * mm, 22 * mm,
                                   16 * mm, 27 * mm, 24 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D4E8")),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    totals = Table([
        ["Sub-total (taxable)", "Rs. %.2f" % invoice["subtotal"]],
        ["CGST", "Rs. %.2f" % cgst],
        ["SGST", "Rs. %.2f" % sgst],
        ["GRAND TOTAL", "Rs. %.2f" % invoice["grand_total"]],
    ], colWidths=[50 * mm, 35 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
        ("BACKGROUND", (0, 3), (-1, 3), soft),
        ("LINEABOVE", (0, 3), (-1, 3), 0.8, navy),
    ]))
    story.append(totals)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("This is a computer-generated invoice. "
                           "CGST and SGST apply to sales within the same State / UT.",
                           center))
    doc.build(story)
    return buffer.getvalue()


def _esc(text):
    """Escape characters that reportlab Paragraph treats as markup."""
    text = "" if text is None else str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
