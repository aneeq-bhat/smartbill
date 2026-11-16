"""
app.py - SmartBill: GST Billing and Inventory Management System (Flask).

Class XII Computer Science (083) project. The web pages only show data;
every calculation, SQL query, file operation and validation is done here in
Python, exactly as in the console version described in the project report.
"""
import calendar
import datetime
import hmac
import logging
import re
import secrets
import time
from decimal import Decimal, InvalidOperation

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, send_from_directory, session, url_for)
from mysql.connector import Error
from mysql.connector.errors import IntegrityError

from config import Config
from db import execute, fetch_all, fetch_one, get_connection, init_db
from utils.csv_export import export_sales_register
from utils.gst import (GST_SLABS, calculate_invoice, calculate_item, money,
                       split_gst)
from utils.invoice_generator import (build_invoice_pdf, build_invoice_text,
                                     save_invoice_text)

app = Flask(__name__)
app.config.from_object(Config)
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(hours=12)
logging.basicConfig(level=logging.INFO)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MAX_STOCK = 10_000_000
MAX_PRICE = Decimal("99999999.99")
MAX_LINES = 50
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PHONE_PATTERN = re.compile(r"^\+?[0-9]{10,13}$")

PUBLIC_ENDPOINTS = {"login", "static", "service_worker", "healthz"}
failed_logins = {}           # {ip address: [times of failed attempts]}


# =========================================================================
# Small helper functions (validation, formatting)
# =========================================================================
class ValidationError(Exception):
    """Raised when a value typed by the user is not acceptable."""


class BillingError(Exception):
    """Raised when an invoice cannot be created (stock, product, customer)."""


def today():
    """Today's date in Indian Standard Time."""
    return datetime.datetime.now(IST).date()


def clean_text(value, label, max_len, required=True):
    """Trim and check a text value; extra spaces are removed."""
    text = " ".join((value or "").split())
    if required and not text:
        raise ValidationError("%s is required." % label)
    if len(text) > max_len:
        raise ValidationError("%s can have at most %d characters." % (label, max_len))
    return text


def parse_int(value, label, minimum=0, maximum=MAX_STOCK):
    """Convert text to a whole number inside the allowed range."""
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValidationError("%s must be a whole number." % label)
    if number < minimum or number > maximum:
        raise ValidationError("%s must be between %d and %d." % (label, minimum, maximum))
    return number


def parse_price(value):
    """Convert text to a price with 2 decimal places."""
    try:
        price = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValidationError("Price must be a number.")
    if not price.is_finite() or price <= 0 or price > MAX_PRICE:
        raise ValidationError("Price must be greater than 0 and at most 99999999.99.")
    return money(price)


def parse_phone(value):
    """Return a cleaned phone number, or None when it is left blank."""
    phone = (value or "").replace(" ", "").replace("-", "")
    if not phone:
        return None
    if not PHONE_PATTERN.match(phone):
        raise ValidationError("Phone must have 10 to 13 digits (optional + at the start).")
    return phone


def parse_gstin(value):
    """Return an upper-case GSTIN, or None when it is left blank."""
    gstin = (value or "").strip().upper()
    if not gstin:
        return None
    if not GSTIN_PATTERN.match(gstin):
        raise ValidationError("GSTIN must be 15 characters, for example 01ABCDE1234F1Z5.")
    return gstin


def parse_date(value, default):
    """Convert YYYY-MM-DD text to a date; use the default if it is invalid."""
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return default


def escape_like(text):
    """Escape % and _ so they are searched as ordinary characters."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def format_inr(value, symbol=True):
    """Format money in the Indian style, e.g. 1,23,456.50."""
    amount = money(value if value is not None else 0)
    sign = "-" if amount < 0 else ""
    whole, fraction = ("%.2f" % abs(amount)).split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return "%s%s%s.%s" % (sign, "\u20b9" if symbol else "", whole, fraction)


def shop_info():
    """Shop details printed on invoices."""
    return {"name": Config.SHOP_NAME, "address": Config.SHOP_ADDRESS,
            "gstin": Config.SHOP_GSTIN, "phone": Config.SHOP_PHONE}


def csrf_token():
    """Return the CSRF token of this session (created when missing)."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.filters["inr"] = format_inr
app.jinja_env.filters["amt"] = lambda v: format_inr(v, symbol=False)
app.jinja_env.filters["month_name"] = lambda m: calendar.month_abbr[int(m)]


@app.context_processor
def inject_globals():
    return {"shop": shop_info(), "low_limit": Config.LOW_STOCK_LIMIT,
            "gst_slabs": GST_SLABS, "current_date": today()}


# =========================================================================
# Security: login check, CSRF check, response headers, error pages
# =========================================================================
@app.before_request
def protect_pages():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400)
    if request.endpoint not in PUBLIC_ENDPOINTS and not session.get("logged_in"):
        return redirect(url_for("login"))


@app.after_request
def add_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.errorhandler(Error)
def database_error(err):
    """Any MySQL error is logged; the user sees only a general message."""
    app.logger.error("Database error: %s", err)
    return render_template("error.html", code=500, title="Database problem",
                           message="SmartBill could not complete the database "
                                   "operation. Please check the database "
                                   "settings and try again."), 500


@app.errorhandler(400)
def bad_request(err):
    return render_template("error.html", code=400, title="Request not accepted",
                           message="The form could not be verified. Reload the "
                                   "page and try again."), 400


@app.errorhandler(404)
def not_found(err):
    return render_template("error.html", code=404, title="Page not found",
                           message="The page you asked for does not exist."), 404


@app.errorhandler(500)
def server_error(err):
    return render_template("error.html", code=500, title="Something went wrong",
                           message="An unexpected error occurred."), 500


# =========================================================================
# Login / logout / service worker / health check
# =========================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        now = time.time()
        recent = [t for t in failed_logins.get(ip, []) if now - t < 600]
        failed_logins[ip] = recent
        if len(recent) >= 5:
            flash("Too many failed attempts. Please wait 10 minutes.", "danger")
        elif not Config.ADMIN_PASSWORD:
            flash("Login is not set up. Set ADMIN_PASSWORD in the environment.", "danger")
        else:
            user_ok = hmac.compare_digest(request.form.get("username", "").encode(),
                                          Config.ADMIN_USERNAME.encode())
            pass_ok = hmac.compare_digest(request.form.get("password", "").encode(),
                                          Config.ADMIN_PASSWORD.encode())
            if user_ok and pass_ok:
                failed_logins.pop(ip, None)
                session.clear()
                session["logged_in"] = True
                session.permanent = True
                return redirect(url_for("dashboard"))
            failed_logins[ip].append(now)
            flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/service-worker.js")
def service_worker():
    """Served from the site root so that it can control every page."""
    response = send_from_directory(app.static_folder, "service-worker.js",
                                   mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/healthz")
def healthz():
    return "ok"


# =========================================================================
# Dashboard
# =========================================================================
@app.route("/")
def dashboard():
    totals = fetch_one("SELECT COUNT(*) AS invoices, "
                       "COALESCE(SUM(grand_total), 0) AS sales, "
                       "COALESCE(AVG(grand_total), 0) AS average "
                       "FROM invoices")
    product_count = fetch_one("SELECT COUNT(*) AS n FROM products")["n"]
    today_sales = fetch_one("SELECT COALESCE(SUM(grand_total), 0) AS s "
                            "FROM invoices WHERE inv_date = %s", (today(),))["s"]
    low_total = fetch_one("SELECT COUNT(*) AS n FROM products WHERE stock < %s",
                          (Config.LOW_STOCK_LIMIT,))["n"]
    low_items = fetch_all("SELECT pid, name, stock FROM products WHERE stock < %s "
                          "ORDER BY stock, name LIMIT 6", (Config.LOW_STOCK_LIMIT,))
    recent = fetch_all("SELECT i.inv_no, i.inv_date, c.name AS customer_name, "
                       "i.grand_total FROM invoices i JOIN customers c "
                       "ON i.cid = c.cid ORDER BY i.inv_no DESC LIMIT 8")
    return render_template("dashboard.html", totals=totals,
                           product_count=product_count, today_sales=today_sales,
                           low_total=low_total, low_items=low_items, recent=recent)


# =========================================================================
# Product management
# =========================================================================
def read_product_form(form):
    """Validate the product form; return a dictionary of clean values."""
    name = clean_text(form.get("name"), "Product name", 50)
    category = clean_text(form.get("category"), "Category", 30, required=False)
    price = parse_price(form.get("price"))
    gst_rate = parse_int(form.get("gst_rate"), "GST rate", 0, 28)
    if gst_rate not in GST_SLABS:
        raise ValidationError("GST rate must be one of 0, 5, 12, 18 or 28.")
    stock = parse_int(form.get("stock"), "Stock", 0, MAX_STOCK)
    return {"name": name, "category": category or None, "price": price,
            "gst_rate": gst_rate, "stock": stock}


@app.route("/products")
def products():
    q = request.args.get("q", "").strip()[:50]
    category = request.args.get("category", "").strip()[:30]
    sql = "SELECT pid, name, category, price, gst_rate, stock FROM products WHERE 1 = 1"
    params = []
    if q:
        like = "%" + escape_like(q) + "%"
        sql += " AND (name LIKE %s OR category LIKE %s)"
        params += [like, like]
    if category:
        sql += " AND category = %s"
        params.append(category)
    sql += " ORDER BY name"
    rows = fetch_all(sql, tuple(params))
    categories = fetch_all("SELECT DISTINCT category FROM products "
                           "WHERE category IS NOT NULL AND category <> '' "
                           "ORDER BY category")
    return render_template("products.html", products=rows, categories=categories,
                           q=q, selected_category=category)


@app.route("/products/add", methods=["GET", "POST"])
def add_product():
    form = {}
    if request.method == "POST":
        form = request.form.to_dict()
        try:
            data = read_product_form(request.form)
            execute("INSERT INTO products (name, category, price, gst_rate, stock) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (data["name"], data["category"], data["price"],
                     data["gst_rate"], data["stock"]))
            flash("Product added successfully.", "success")
            return redirect(url_for("products"))
        except ValidationError as err:
            flash(str(err), "danger")
    return render_template("add_product.html", product=None, form=form,
                           categories=category_list())


@app.route("/products/<int:pid>/edit", methods=["GET", "POST"])
def edit_product(pid):
    product = fetch_one("SELECT pid, name, category, price, gst_rate, stock "
                        "FROM products WHERE pid = %s", (pid,))
    if product is None:
        abort(404)
    form = {}
    if request.method == "POST":
        form = request.form.to_dict()
        try:
            data = read_product_form(request.form)
            execute("UPDATE products SET name = %s, category = %s, price = %s, "
                    "gst_rate = %s, stock = %s WHERE pid = %s",
                    (data["name"], data["category"], data["price"],
                     data["gst_rate"], data["stock"], pid))
            flash("Product updated.", "success")
            return redirect(url_for("products"))
        except ValidationError as err:
            flash(str(err), "danger")
    return render_template("add_product.html", product=product, form=form,
                           categories=category_list())


@app.route("/products/<int:pid>/delete", methods=["POST"])
def delete_product(pid):
    try:
        _, deleted = execute("DELETE FROM products WHERE pid = %s", (pid,))
        if deleted:
            flash("Product deleted.", "success")
        else:
            flash("Product not found.", "warning")
    except IntegrityError:
        flash("This product appears on saved invoices, so it cannot be deleted. "
              "Set its stock to 0 instead.", "warning")
    return redirect(url_for("products"))


def category_list():
    """Existing category names (used for suggestions in the product form)."""
    rows = fetch_all("SELECT DISTINCT category FROM products "
                     "WHERE category IS NOT NULL AND category <> '' ORDER BY category")
    return [r["category"] for r in rows]


# =========================================================================
# Customer management
# =========================================================================
def read_customer_form(form):
    name = clean_text(form.get("name"), "Customer name", 50)
    return name, parse_phone(form.get("phone")), parse_gstin(form.get("gstin"))


@app.route("/customers", methods=["GET", "POST"])
def customers():
    form = {}
    if request.method == "POST":
        form = request.form.to_dict()
        try:
            name, phone, gstin = read_customer_form(request.form)
            cid, _ = execute("INSERT INTO customers (name, phone, gstin) "
                             "VALUES (%s, %s, %s)", (name, phone, gstin))
            flash("Customer added with ID %d." % cid, "success")
            return redirect(url_for("customers"))
        except ValidationError as err:
            flash(str(err), "danger")
    q = request.args.get("q", "").strip()[:50]
    sql = "SELECT cid, name, phone, gstin FROM customers"
    params = ()
    if q:
        like = "%" + escape_like(q) + "%"
        sql += " WHERE name LIKE %s OR phone LIKE %s OR gstin LIKE %s"
        params = (like, like, like)
    rows = fetch_all(sql + " ORDER BY cid", params)
    edit_customer = None
    edit_id = request.args.get("edit", "")
    if edit_id.isdigit():
        edit_customer = fetch_one("SELECT cid, name, phone, gstin FROM customers "
                                  "WHERE cid = %s", (int(edit_id),))
    return render_template("customers.html", customers=rows, q=q, form=form,
                           edit_customer=edit_customer)


@app.route("/customers/<int:cid>/edit", methods=["POST"])
def edit_customer(cid):
    try:
        name, phone, gstin = read_customer_form(request.form)
        if fetch_one("SELECT cid FROM customers WHERE cid = %s", (cid,)) is None:
            abort(404)
        execute("UPDATE customers SET name = %s, phone = %s, gstin = %s "
                "WHERE cid = %s", (name, phone, gstin, cid))
        flash("Customer updated.", "success")
        return redirect(url_for("customers"))
    except ValidationError as err:
        flash(str(err), "danger")
        return redirect(url_for("customers", edit=cid))


# =========================================================================
# Billing (invoice creation inside one database transaction)
# =========================================================================
def parse_cart(form):
    """
    Read the product IDs and quantities from the billing form.
    Returns a dictionary {product id: quantity}; repeated products are added.
    """
    pids = form.getlist("pid")
    qtys = form.getlist("qty")
    if len(pids) != len(qtys) or len(pids) > MAX_LINES:
        raise BillingError("The invoice lines are not valid.")
    cart = {}
    for raw_pid, raw_qty in zip(pids, qtys):
        if not raw_pid.strip() and not raw_qty.strip():
            continue
        try:
            pid = parse_int(raw_pid, "Product", 1, 2_000_000_000)
            qty = parse_int(raw_qty, "Quantity", 1, 100_000)
        except ValidationError as err:
            raise BillingError(str(err))
        cart[pid] = cart.get(pid, 0) + qty
    if not cart:
        raise BillingError("Add at least one product to the invoice.")
    return cart


def create_invoice(cid, cart):
    """
    Create an invoice, its items and the stock deduction as ONE transaction.
    Either everything is saved (commit) or nothing is saved (rollback).
    Prices and GST rates are read from the database, never from the browser.
    """
    con = get_connection()
    try:
        cur = con.cursor(dictionary=True)
        cur.execute("SELECT cid FROM customers WHERE cid = %s", (cid,))
        if cur.fetchone() is None:
            raise BillingError("No such customer.")

        lines = []
        for pid in sorted(cart):             # fixed order avoids deadlocks
            qty = cart[pid]
            cur.execute("SELECT pid, name, price, gst_rate, stock FROM products "
                        "WHERE pid = %s FOR UPDATE", (pid,))
            row = cur.fetchone()
            if row is None:
                raise BillingError("Invalid product ID %d." % pid)
            if qty > row["stock"]:
                raise BillingError("Only %d unit(s) of %s in stock."
                                   % (row["stock"], row["name"]))
            line = calculate_item(row["price"], qty, row["gst_rate"])
            line["pid"] = pid
            lines.append(line)

        totals = calculate_invoice(lines)
        cur.execute("INSERT INTO invoices (cid, inv_date, subtotal, total_gst, "
                    "grand_total) VALUES (%s, %s, %s, %s, %s)",
                    (cid, today(), totals["subtotal"], totals["total_gst"],
                     totals["grand_total"]))
        inv_no = cur.lastrowid
        for line in lines:
            cur.execute("INSERT INTO invoice_items (inv_no, pid, qty, rate, "
                        "gst_rate, taxable, gst_amt) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (inv_no, line["pid"], line["qty"], line["rate"],
                         line["gst_rate"], line["taxable"], line["gst_amt"]))
            cur.execute("UPDATE products SET stock = stock - %s "
                        "WHERE pid = %s AND stock >= %s",
                        (line["qty"], line["pid"], line["qty"]))
            if cur.rowcount != 1:
                raise BillingError("Stock changed while billing. Please try again.")
        con.commit()
        return inv_no
    except (BillingError, Error):
        con.rollback()
        raise
    finally:
        con.close()


def render_billing(selected_cid=1, prefill=None):
    product_rows = fetch_all("SELECT pid, name, category, price, gst_rate, stock "
                             "FROM products ORDER BY name")
    client_products = [{"pid": p["pid"], "name": p["name"],
                        "category": p["category"] or "",
                        "price": float(p["price"]), "gst": p["gst_rate"],
                        "stock": p["stock"]} for p in product_rows]
    customer_rows = fetch_all("SELECT cid, name, phone FROM customers "
                              "ORDER BY cid = 1 DESC, name")
    return render_template("billing.html", client_products=client_products,
                           customers=customer_rows, selected_cid=selected_cid,
                           prefill=prefill or [])


@app.route("/billing", methods=["GET", "POST"])
def billing():
    if request.method == "GET":
        return render_billing()
    selected_cid = 1
    prefill = []
    try:
        selected_cid = parse_int(request.form.get("cid"), "Customer", 1, 2_000_000_000)
        for raw_pid, raw_qty in zip(request.form.getlist("pid"),
                                    request.form.getlist("qty")):
            if raw_pid.strip().isdigit() and raw_qty.strip().isdigit():
                prefill.append({"pid": int(raw_pid), "qty": int(raw_qty)})
        cart = parse_cart(request.form)
        inv_no = create_invoice(selected_cid, cart)
    except (BillingError, ValidationError) as err:
        flash(str(err), "danger")
        return render_billing(selected_cid, prefill)
    invoice, items = load_invoice(inv_no)
    try:                                     # also keep a text copy of the bill
        save_invoice_text(inv_no, build_invoice_text(invoice, items, shop_info()),
                          Config.EXPORT_DIR)
    except OSError as err:
        app.logger.warning("Could not save invoice text file: %s", err)
    flash("Invoice %d created." % inv_no, "success")
    return redirect(url_for("view_invoice", inv_no=inv_no))


# =========================================================================
# Invoices
# =========================================================================
def load_invoice(inv_no):
    """Rebuild an invoice from the database using SQL JOINs."""
    invoice = fetch_one(
        "SELECT i.inv_no, i.inv_date, i.subtotal, i.total_gst, i.grand_total, "
        "c.cid, c.name AS customer_name, c.phone, c.gstin "
        "FROM invoices i JOIN customers c ON i.cid = c.cid "
        "WHERE i.inv_no = %s", (inv_no,))
    if invoice is None:
        return None, []
    items = fetch_all(
        "SELECT t.item_id, p.name, t.qty, t.rate, t.gst_rate, t.taxable, t.gst_amt "
        "FROM invoice_items t JOIN products p ON t.pid = p.pid "
        "WHERE t.inv_no = %s ORDER BY t.item_id", (inv_no,))
    return invoice, items


@app.route("/invoices")
def invoices():
    q = request.args.get("q", "").strip()[:50]
    start = parse_date(request.args.get("from"), None)
    end = parse_date(request.args.get("to"), None)
    sql = ("SELECT i.inv_no, i.inv_date, c.name AS customer_name, i.subtotal, "
           "i.total_gst, i.grand_total FROM invoices i "
           "JOIN customers c ON i.cid = c.cid WHERE 1 = 1")
    params = []
    if q:
        like = "%" + escape_like(q) + "%"
        if q.isdigit():
            sql += " AND (i.inv_no = %s OR c.name LIKE %s)"
            params += [int(q), like]
        else:
            sql += " AND c.name LIKE %s"
            params.append(like)
    if start:
        sql += " AND i.inv_date >= %s"
        params.append(start)
    if end:
        sql += " AND i.inv_date <= %s"
        params.append(end)
    rows = fetch_all(sql + " ORDER BY i.inv_no DESC LIMIT 200", tuple(params))
    return render_template("invoices.html", invoices=rows, q=q,
                           start=start, end=end)


@app.route("/invoices/<int:inv_no>")
def view_invoice(inv_no):
    invoice, items = load_invoice(inv_no)
    if invoice is None:
        abort(404)
    cgst, sgst = split_gst(invoice["total_gst"])
    return render_template("invoice.html", invoice=invoice, items=items,
                           cgst=cgst, sgst=sgst)


@app.route("/invoices/<int:inv_no>/download.txt")
def download_invoice_txt(inv_no):
    invoice, items = load_invoice(inv_no)
    if invoice is None:
        abort(404)
    text = build_invoice_text(invoice, items, shop_info())
    try:
        save_invoice_text(inv_no, text, Config.EXPORT_DIR)
    except OSError as err:
        app.logger.warning("Could not save invoice text file: %s", err)
    return Response(text, mimetype="text/plain; charset=utf-8", headers={
        "Content-Disposition": "attachment; filename=invoice_%d.txt" % inv_no})


@app.route("/invoices/<int:inv_no>/download.pdf")
def download_invoice_pdf(inv_no):
    invoice, items = load_invoice(inv_no)
    if invoice is None:
        abort(404)
    pdf_bytes = build_invoice_pdf(invoice, items, shop_info())
    return Response(pdf_bytes, mimetype="application/pdf", headers={
        "Content-Disposition": "attachment; filename=invoice_%d.pdf" % inv_no})


# =========================================================================
# Inventory
# =========================================================================
@app.route("/inventory")
def inventory():
    only_low = request.args.get("low") == "1"
    sql = "SELECT pid, name, category, stock, price FROM products"
    params = ()
    if only_low:
        sql += " WHERE stock < %s"
        params = (Config.LOW_STOCK_LIMIT,)
    rows = fetch_all(sql + " ORDER BY stock, name", params)
    summary = fetch_one("SELECT COUNT(*) AS products, COALESCE(SUM(stock), 0) AS units, "
                        "COALESCE(SUM(stock * price), 0) AS value FROM products")
    return render_template("inventory.html", products=rows, only_low=only_low,
                           summary=summary)


@app.route("/inventory/<int:pid>/update", methods=["POST"])
def update_inventory(pid):
    only_low = request.form.get("low") == "1"
    try:
        mode = request.form.get("mode", "")
        qty = parse_int(request.form.get("qty"), "Quantity", 0, MAX_STOCK)
        product = fetch_one("SELECT stock FROM products WHERE pid = %s", (pid,))
        if product is None:
            raise ValidationError("Product not found.")
        if mode == "add":
            if qty < 1:
                raise ValidationError("Enter at least 1 unit to add.")
            new_stock = product["stock"] + qty
        elif mode == "set":
            new_stock = qty
        else:
            raise ValidationError("Choose 'Add units' or 'Set stock'.")
        if new_stock > MAX_STOCK:
            raise ValidationError("Stock cannot be more than %d." % MAX_STOCK)
        execute("UPDATE products SET stock = %s WHERE pid = %s", (new_stock, pid))
        flash("Stock updated. New stock: %d." % new_stock, "success")
    except ValidationError as err:
        flash(str(err), "danger")
    return redirect(url_for("inventory", low="1" if only_low else None))


# =========================================================================
# GST and sales reports
# =========================================================================
def report_range():
    """Read the from/to dates of the report (default: this month so far)."""
    end_default = today()
    start_default = end_default.replace(day=1)
    start = parse_date(request.args.get("from"), start_default)
    end = parse_date(request.args.get("to"), end_default)
    if start > end:
        flash("The 'from' date was after the 'to' date, so they were swapped.", "warning")
        start, end = end, start
    return start, end


def sales_register(start, end):
    """Every invoice between two dates (JOIN of invoices and customers)."""
    return fetch_all("SELECT i.inv_no, i.inv_date, c.name AS customer_name, "
                     "i.subtotal, i.total_gst, i.grand_total "
                     "FROM invoices i JOIN customers c ON i.cid = c.cid "
                     "WHERE i.inv_date BETWEEN %s AND %s ORDER BY i.inv_no",
                     (start, end))


@app.route("/reports")
def reports():
    start, end = report_range()
    span = (start, end)
    totals = fetch_one("SELECT COUNT(*) AS invoices, "
                       "COALESCE(SUM(subtotal), 0) AS taxable, "
                       "COALESCE(SUM(total_gst), 0) AS gst, "
                       "COALESCE(SUM(grand_total), 0) AS revenue, "
                       "COALESCE(AVG(grand_total), 0) AS average "
                       "FROM invoices WHERE inv_date BETWEEN %s AND %s", span)

    # GST-wise summary: JOIN + SUM + GROUP BY (as in gst_report() of the report)
    gst_rows = fetch_all("SELECT t.gst_rate, COUNT(DISTINCT t.inv_no) AS invoices, "
                         "SUM(t.qty) AS units, SUM(t.taxable) AS taxable, "
                         "SUM(t.gst_amt) AS gst "
                         "FROM invoice_items t JOIN invoices i ON t.inv_no = i.inv_no "
                         "WHERE i.inv_date BETWEEN %s AND %s "
                         "GROUP BY t.gst_rate ORDER BY t.gst_rate", span)
    gst_total = {"taxable": Decimal("0.00"), "cgst": Decimal("0.00"),
                 "sgst": Decimal("0.00"), "gst": Decimal("0.00")}
    for row in gst_rows:
        row["cgst"], row["sgst"] = split_gst(row["gst"])
        gst_total["taxable"] += row["taxable"]
        gst_total["cgst"] += row["cgst"]
        gst_total["sgst"] += row["sgst"]
        gst_total["gst"] += row["gst"]

    # Date-wise report (daily sales and GST): GROUP BY inv_date
    daily = fetch_all("SELECT inv_date, COUNT(*) AS invoices, "
                      "SUM(subtotal) AS taxable, SUM(total_gst) AS gst, "
                      "SUM(grand_total) AS total FROM invoices "
                      "WHERE inv_date BETWEEN %s AND %s "
                      "GROUP BY inv_date ORDER BY inv_date", span)
    for row in daily:
        row["cgst"], row["sgst"] = split_gst(row["gst"])

    # Monthly sales: GROUP BY year and month, with COUNT, SUM and AVG
    monthly = fetch_all("SELECT YEAR(inv_date) AS yr, MONTH(inv_date) AS mon, "
                        "COUNT(*) AS invoices, SUM(grand_total) AS total, "
                        "AVG(grand_total) AS average FROM invoices "
                        "WHERE inv_date BETWEEN %s AND %s "
                        "GROUP BY YEAR(inv_date), MONTH(inv_date) "
                        "ORDER BY yr, mon", span)

    # Best-selling products: GROUP BY with HAVING
    top_products = fetch_all("SELECT p.name, SUM(t.qty) AS units, "
                             "SUM(t.taxable) AS taxable "
                             "FROM invoice_items t "
                             "JOIN products p ON t.pid = p.pid "
                             "JOIN invoices i ON t.inv_no = i.inv_no "
                             "WHERE i.inv_date BETWEEN %s AND %s "
                             "GROUP BY p.pid, p.name HAVING SUM(t.qty) >= %s "
                             "ORDER BY units DESC, p.name LIMIT 10", (start, end, 1))

    register = sales_register(start, end)
    for row in register:
        row["cgst"], row["sgst"] = split_gst(row["total_gst"])

    t = today()
    presets = [("Today", t, t),
               ("This month", t.replace(day=1), t),
               ("This year", t.replace(month=1, day=1), t),
               ("All time", datetime.date(2000, 1, 1), t)]
    return render_template("reports.html", start=start, end=end, totals=totals,
                           gst_rows=gst_rows, gst_total=gst_total, daily=daily,
                           monthly=monthly, top_products=top_products,
                           register=register, presets=presets)


@app.route("/reports/export.csv")
def export_csv():
    start, end = report_range()
    register = sales_register(start, end)
    try:
        data = export_sales_register(register, Config.EXPORT_DIR)
    except OSError as err:
        app.logger.error("CSV export failed: %s", err)
        flash("The CSV file could not be written on the server.", "danger")
        return redirect(url_for("reports", **{"from": start, "to": end}))
    name = "sales_register_%s_to_%s.csv" % (start.isoformat(), end.isoformat())
    return Response(data, mimetype="text/csv; charset=utf-8", headers={
        "Content-Disposition": "attachment; filename=" + name})


# =========================================================================
# Start-up
# =========================================================================
def initialise_database():
    """Create the tables on start-up. A failure is logged, not fatal."""
    try:
        init_db()
        app.logger.info("Database ready.")
    except (Error, OSError, ValueError) as err:
        app.logger.error("Database initialisation failed: %s", err)


@app.cli.command("init-db")
def init_db_command():
    """Create the database tables: flask --app app init-db"""
    init_db()
    print("Tables created (or already present).")


if not Config.SECRET_KEY_FROM_ENV:
    app.logger.warning("SECRET_KEY is not set; a temporary key is being used.")
if not Config.ADMIN_PASSWORD:
    app.logger.warning("ADMIN_PASSWORD is not set; login is disabled.")
initialise_database()

if __name__ == "__main__":
    import os
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
