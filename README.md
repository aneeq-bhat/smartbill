# SmartBill - GST Billing and Inventory Management System

A responsive, mobile-friendly web version of the **SmartBill** Class XII Computer Science (083) project.
It keeps the same four MySQL tables, the same GST formulas and the same invoice layout as the project
report, and adds a Flask web interface that works on Android, iPhone, tablets and desktop browsers.
It can also be installed on a phone or computer as a Progressive Web App (PWA).

* **Backend:** Python 3 + Flask (all calculations, SQL, validation and file handling are done in Python)
* **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5 (loaded from the jsDelivr CDN)
* **Database:** MySQL 8 through `mysql-connector-python`
* **Production server:** Gunicorn, deployed on Render with an external MySQL database

---

## 1. Folder structure

```
smartbill/
├── app.py                  Flask app: routes, validation, invoice transaction, reports
├── db.py                   Python-MySQL connectivity, parameterised-query helpers, init_db()
├── config.py               Settings read from environment variables (no secrets in code)
├── schema.sql              CREATE TABLE statements for the 4 tables
├── requirements.txt        Python packages (exact versions that were tested)
├── .env.example            Template for your private .env file
├── .gitignore
├── README.md
├── templates/              base, login, dashboard, products, add_product, customers,
│                           billing, invoice, inventory, reports (+ invoices, error)
├── static/
│   ├── css/style.css       Navy/blue POS theme, responsive layout, print styles
│   ├── js/app.js           Billing screen, confirmations, service-worker registration
│   ├── images/             PWA icons
│   ├── manifest.json       PWA manifest
│   └── service-worker.js   PWA service worker (caches static files only)
├── utils/
│   ├── gst.py              GST formulas (Decimal arithmetic)
│   ├── invoice_generator.py  Invoice TXT (file handling) and PDF
│   └── csv_export.py       Sales register CSV (csv module)
└── exports/                Saved invoice_N.txt and sales_register.csv (contents not committed)
```

Two small extra templates were added: `invoices.html` (list/search of old invoices) and `error.html`.

## 2. How the web app maps to your report

| Report function (console) | Web page / route | Where in the code |
|---|---|---|
| `setup()` | runs automatically at start-up | `db.init_db()` + `schema.sql` |
| `connect()` | every query | `db.get_connection()` |
| `add_product()` / `view_products()` | Products, Add/Edit product | `/products`, `/products/add`, `/products/<id>/edit` |
| `low_stock()` | Dashboard card, Inventory "Low stock" | `/inventory?low=1` |
| `add_customer()` | Customers | `/customers`, `/customers/<id>/edit` |
| `create_invoice()` | Billing (New Invoice) | `create_invoice()` in `app.py` |
| `show_invoice()` | Invoice page, TXT and PDF download | `/invoices/<no>`, `load_invoice()` |
| `gst_report()` | Reports > GST summary | `/reports` |
| `export_csv()` | Reports > Export CSV | `/reports/export.csv`, `utils/csv_export.py` |

The database design is unchanged: `products`, `customers`, `invoices`, `invoice_items` with the same
columns, primary keys and foreign keys (`invoices.cid -> customers.cid`, `invoice_items.inv_no ->
invoices.inv_no`, `invoice_items.pid -> products.pid`). The walk-in customer is customer ID 1.

## 3. Where each CBSE Class XII concept is used

| Concept | Where to find it |
|---|---|
| Python functions | every function in `app.py`, `db.py`, `utils/*.py` |
| Lists and dictionaries | `parse_cart()` (dictionary `{pid: qty}`), `calculate_invoice()` (list of line dictionaries), report rows |
| Conditions and loops | `calculate_invoice()`, `create_invoice()`, `format_inr()`, `build_invoice_text()` |
| Exception handling | `try/except` in `create_invoice()`, `delete_product()`, billing/CSV routes, `ValidationError`, `BillingError`, `mysql.connector.Error` handler |
| Text file handling | `save_invoice_text()` writes `exports/invoice_N.txt` (`open(..., "w")`, `f.write`) |
| CSV file handling | `export_sales_register()` uses `csv.writer`, `writerow`, `writerows` |
| Python-MySQL connectivity | `db.py`: `connect()`, `cursor()`, `execute()`, `fetchall()`, `commit()`, `rollback()`, `lastrowid` |
| SQL DDL | `CREATE TABLE` in `schema.sql` |
| SQL DML | `INSERT`, `UPDATE`, `DELETE`, `SELECT` in `app.py` |
| Aggregate functions | `SUM`, `COUNT`, `AVG` in `dashboard()` and `reports()` |
| GROUP BY / HAVING | `reports()`: GST rate-wise, date-wise, monthly, and top products (`HAVING SUM(t.qty) >= %s`) |
| JOIN | invoice loading, GST report, sales register, top products |
| Transactions | `create_invoice()` - invoice, items and stock change are committed together or rolled back |
| Parameterised queries | every query uses `%s` placeholders; values are never joined into SQL text |

## 4. Run it on your own computer

### 4.1 Install the tools
* Python 3.10 or newer (3.12 was used for testing)
* MySQL Server 8.0 and its command-line client

### 4.2 Create the database and a MySQL user
Log in to MySQL (`mysql -u root -p`) and run:

```sql
CREATE DATABASE smartbill CHARACTER SET utf8mb4;
CREATE USER 'smartbill'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON smartbill.* TO 'smartbill'@'localhost';
```

(You do not have to run `schema.sql` yourself: the app creates the tables when it starts. You may also
use `mysql -u root -p < schema.sql` after uncommenting the first two lines of that file.)

### 4.3 Install and configure

```bash
cd smartbill
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt

# Windows:        copy .env.example .env
# macOS / Linux:  cp .env.example .env
```

Open `.env` in an editor and set at least `SECRET_KEY`, `ADMIN_PASSWORD`, `DB_USER`, `DB_PASSWORD`
and `DB_NAME`. Create a secret key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4.4 Start the app

```bash
python app.py
```

Open <http://127.0.0.1:5000> and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from your `.env`.
To test on your phone while on the same Wi-Fi, run
`flask --app app run --host 0.0.0.0` and open `http://<your-computer-IP>:5000`. (This is only for
testing on a trusted network.)

### 4.5 First steps in the app
1. **Products > Add product** - for example Basmati Rice 5kg, Grocery, 450, 5%, stock 50.
2. **Customers** - optional. "Walk-in Customer" (ID 1) already exists.
3. **New Invoice** - tap products to add them, adjust quantities, choose the customer, **Save invoice**.
4. On the invoice page use **Print**, **PDF** or **TXT**.
5. **Reports** - choose dates, see the GST summary, daily/monthly sales, top products, sales register,
   and **Export sales register (CSV)**.

## 5. Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `SECRET_KEY` | **Yes** (production) | Signs login sessions. Without it a random key is used and you are logged out at every restart. |
| `ADMIN_USERNAME` | No (default `admin`) | Login name |
| `ADMIN_PASSWORD` | **Yes** | Login password. If empty, login is disabled. |
| `DB_HOST`, `DB_PORT` | **Yes** (hosted DB) | MySQL server address and port (default `localhost`, `3306`) |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME` | **Yes** | MySQL credentials and database name (default name `smartbill`) |
| `DB_SSL_CA` / `DB_SSL_CA_PEM` | Only if your provider needs it | Path to a CA file, or the certificate text itself (use `\n` for line breaks) |
| `SESSION_COOKIE_SECURE` | Set `1` on Render | Sends the login cookie only over HTTPS |
| `SHOP_NAME`, `SHOP_ADDRESS`, `SHOP_PHONE`, `SHOP_GSTIN` | No | Printed on invoices |
| `LOW_STOCK_LIMIT` | No (default 10) | Stock below this number is "low stock" |
| `PYTHON_VERSION` | Render only | Use a full version such as `3.12.3` (the version used for testing) |

## 6. Put the project on GitHub

1. Create an empty **private** repository on github.com (for example `smartbill`). Do not add a README there.
2. In the project folder run:

```bash
git init
git add .
git status          # check that .env is NOT in the list
git commit -m "SmartBill web application"
git branch -M main
git remote add origin https://github.com/<your-username>/smartbill.git
git push -u origin main
```

`.gitignore` already excludes `.env`, `__pycache__`, virtual environments and generated export files.
If you ever commit a password by mistake, change that password immediately.

## 7. Deploy on Render with an external MySQL database

Render's web services run your Flask app, but **this project does not assume Render provides MySQL**.
You need a MySQL 8 database from somewhere else (a managed MySQL provider, a cloud VM, or a school/hosting
server) that can be reached from the internet. Check the provider's current plans and prices yourself -
they change often. You need these five values from it: **host, port, user, password, database name**
(and a CA certificate if the provider requires TLS).

### 7.1 Prepare the database
1. Create a MySQL 8 database named `smartbill` (or any name) and a user with full rights on it
   (`SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES` are needed).
2. If the provider has an IP allow-list / firewall, allow your Render service's outbound IP addresses
   (Render lists them in the service's dashboard / documentation) or the provider's "allow all" option.
3. Note the connection values. The app creates the four tables by itself on first start.

### 7.2 Create the Render web service
1. Sign in at <https://render.com> and connect your GitHub account.
2. **New > Web Service**, choose your `smartbill` repository.
3. Fill in:

| Field | Value |
|---|---|
| Language / Runtime | `Python 3` |
| Branch | `main` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60` |
| Health Check Path (Settings) | `/healthz` |

4. Under **Environment Variables** add:

```
PYTHON_VERSION        3.12.3
SECRET_KEY            <long random string from python -c "import secrets; print(secrets.token_hex(32))">
SESSION_COOKIE_SECURE 1
ADMIN_USERNAME        <your login name>
ADMIN_PASSWORD        <a strong password>
DB_HOST               <host from your MySQL provider>
DB_PORT               <port, usually 3306>
DB_USER               <database user>
DB_PASSWORD           <database password>
DB_NAME               <database name>
SHOP_NAME             <your shop name>
SHOP_ADDRESS          <your shop address>
SHOP_GSTIN            <your GSTIN, optional>
```

   If your provider requires a CA certificate, also add `DB_SSL_CA_PEM` with the certificate text
   (replace each line break with `\n`).
5. Click **Create Web Service**. When the build finishes, open the `https://<name>.onrender.com` URL and log in.
6. Check **Logs** on Render: you should see `Database ready.` If you see
   `Database initialisation failed`, re-check the `DB_*` values, the provider's firewall and TLS settings.

### 7.3 Things to know about Render
* **Saved files are temporary.** Render's disk is wiped when the service restarts or redeploys, so
  `exports/invoice_N.txt` and `sales_register.csv` do not last. This does not lose data: all invoices live in MySQL,
  and every PDF/TXT/CSV download is regenerated from the database.
* On some plans the service may go to sleep when idle, so the first page can take a while to load.
* To update the site: `git push` to `main`; Render redeploys automatically (if auto-deploy is on).

## 8. Install as an app (PWA)
Open the deployed `https://` address.
* **Android (Chrome):** menu > *Install app* / *Add to Home screen*.
* **iPhone (Safari):** Share > *Add to Home Screen*.
* **Desktop (Chrome/Edge):** install icon at the right of the address bar.

The service worker caches only the CSS, JavaScript and icons. Pages and data are never cached,
so billing needs an internet connection (an "offline" message is shown otherwise). Bootstrap
is loaded from a CDN, so the first visit also needs internet access.

## 9. What was tested

Tested in the build environment with **Python 3.12.3 and a real MySQL 8.0.46 server**
(strict default `sql_mode`, including `ONLY_FULL_GROUP_BY`), using the exact pinned `requirements.txt`:

* Python syntax and imports (`py_compile`, `pyflakes`), all templates rendered, every `url_for` endpoint exists.
* Table creation on a brand-new database; the four tables, columns and three foreign keys match the report.
* Your report's test data: invoice 1 = 1320.00 + 102.60 GST (CGST 51.30 / SGST 51.30) = **1422.60**;
  invoice 2 = **472.50**; stock **47 / 95 / 7 / 15**; GST summary for 2024-2030 = taxable **1770.00**, GST **125.10**;
  TXT invoice identical to the sample in section 17.2 of the report.
* Stock rules: an over-quantity sale is refused; a failure in the middle of an invoice rolls back the invoice,
  its items and the stock change (tested with a forced database error); 6 simultaneous buyers of the last unit - exactly one succeeds.
* Validation (GST slab, prices, quantities, phone, GSTIN), invalid product/customer IDs, duplicate product lines merged.
* CSV export (header and rows), PDF generation (opens as a valid A4 PDF), TXT file handling.
* Login, CSRF protection, logout, login throttling, HTML escaping of product names.
* Run under Gunicorn with a fresh database.
* The browser-side bill preview gives the same amounts as the Python calculation on 3,000 random invoices, and the
  billing-screen JavaScript was exercised in a simulated DOM (jsdom).

**Not tested:** how the pages look in real browsers or on real Android/iPhone devices (no browser was available,
so mobile responsiveness is built with Bootstrap's grid, a bottom navigation bar and card-style tables, but not yet checked by eye);
PWA installation; an actual Render deployment or any cloud MySQL provider; MySQL versions other than 8.0.46; heavy load.
Please open it on your phone after deploying and tell me if anything looks wrong.

## 10. Limitations
* Intra-state sales only (CGST + SGST). IGST, HSN codes, discounts, returns and invoice cancellation are not included.
* One login account (shop owner). The failed-login limit is kept in memory per server process.
* The invoice date uses Indian Standard Time.
* A product that appears on a saved invoice cannot be deleted (it would break old invoices); set its stock to 0 instead.

## 11. Troubleshooting

| Message / problem | What to check |
|---|---|
| `Access denied for user` | `DB_USER` / `DB_PASSWORD` wrong, or the user has no rights on `DB_NAME` |
| `Can't connect to MySQL server` | `DB_HOST` / `DB_PORT`, MySQL not running, or the provider's firewall blocks Render |
| `Database initialisation failed` in logs | Missing CREATE privilege, wrong database name, or TLS/CA settings |
| "Login is not set up" | Set `ADMIN_PASSWORD` |
| Logged out after every restart | Set a fixed `SECRET_KEY` |
| "The form could not be verified" | The session expired; reload the page and try again |
