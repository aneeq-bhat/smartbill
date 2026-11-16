"""
utils/gst.py - GST calculation logic (from section 10.6 of the project report).

    Taxable value = Rate x Quantity
    GST amount    = Taxable value x GST rate / 100
    CGST = SGST   = Total GST / 2      (sale inside the same State / UT)
    Grand total   = Sum of taxable values + Total GST

Decimal is used instead of float so that money is always exact to the paisa.
"""
from decimal import Decimal, ROUND_HALF_UP

GST_SLABS = (0, 5, 12, 18, 28)
PAISA = Decimal("0.01")


def money(value):
    """Convert a number to a Decimal rounded to 2 places (half up)."""
    return Decimal(str(value)).quantize(PAISA, rounding=ROUND_HALF_UP)


def is_valid_gst_rate(rate):
    """True if the rate is one of the five GST slabs."""
    return rate in GST_SLABS


def calculate_item(rate, qty, gst_rate):
    """Return a dictionary with taxable value and GST for one invoice line."""
    taxable = money(Decimal(str(rate)) * int(qty))
    gst_amt = money(taxable * int(gst_rate) / 100)
    return {"rate": money(rate), "qty": int(qty), "gst_rate": int(gst_rate),
            "taxable": taxable, "gst_amt": gst_amt}


def split_gst(total_gst):
    """Split total GST into CGST and SGST (they always add up exactly)."""
    total_gst = money(total_gst)
    cgst = money(total_gst / 2)
    sgst = total_gst - cgst
    return cgst, sgst


def calculate_invoice(lines):
    """
    lines is a list of dictionaries made by calculate_item().
    Returns subtotal, total GST, CGST, SGST and grand total.
    """
    subtotal = Decimal("0.00")
    total_gst = Decimal("0.00")
    for line in lines:                       # loop over every item
        subtotal += line["taxable"]
        total_gst += line["gst_amt"]
    cgst, sgst = split_gst(total_gst)
    return {"subtotal": subtotal, "total_gst": total_gst,
            "cgst": cgst, "sgst": sgst, "grand_total": subtotal + total_gst}
