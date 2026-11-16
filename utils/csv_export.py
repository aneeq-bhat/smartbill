"""
utils/csv_export.py - CSV file handling for the sales register.

Uses Python's csv module (csv.writer, writerow, writerows) exactly like the
export_csv() function in the project report.
"""
import csv
import os
import threading

from utils.gst import split_gst

HEADER = ["Invoice", "Date", "Customer", "Taxable", "CGST", "SGST",
          "Total GST", "Total"]

_write_lock = threading.Lock()


def _safe_text(text):
    """Stop spreadsheet programs from running text such as =SUM(...)."""
    text = "" if text is None else str(text)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def build_rows(register):
    """Turn rows from the database into a list of CSV rows."""
    rows = []
    for r in register:
        cgst, sgst = split_gst(r["total_gst"])
        rows.append([r["inv_no"], r["inv_date"].isoformat(),
                     _safe_text(r["customer_name"]),
                     r["subtotal"], cgst, sgst, r["total_gst"],
                     r["grand_total"]])
    return rows


def export_sales_register(register, export_dir, filename="sales_register.csv"):
    """
    Write the sales register to export_dir/filename and return the file
    contents as bytes (so the web page can send it as a download).
    """
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, filename)
    with _write_lock:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)
            writer.writerows(build_rows(register))
        with open(path, "rb") as f:
            return f.read()
