-- ============================================================================
-- SmartBill - GST Billing and Inventory Management System
-- MySQL 8 schema (same four tables as the CBSE project report)
--
-- Local use:    mysql -u root -p < schema.sql
-- The app also runs the CREATE TABLE statements below automatically when it
-- starts (db.init_db). On a hosted MySQL service the database already exists,
-- so the two lines below are commented out.
-- ============================================================================

-- CREATE DATABASE IF NOT EXISTS smartbill;
-- USE smartbill;

-- Table 1: products ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    pid       INT AUTO_INCREMENT PRIMARY KEY,
    name      VARCHAR(50)   NOT NULL,
    category  VARCHAR(30),
    price     DECIMAL(10,2) NOT NULL,
    gst_rate  INT           NOT NULL,
    stock     INT           NOT NULL
);

-- Table 2: customers ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    cid    INT AUTO_INCREMENT PRIMARY KEY,
    name   VARCHAR(50) NOT NULL,
    phone  VARCHAR(15),
    gstin  VARCHAR(15)
);

-- Table 3: invoices ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    inv_no       INT AUTO_INCREMENT PRIMARY KEY,
    cid          INT  NOT NULL,
    inv_date     DATE NOT NULL,
    subtotal     DECIMAL(10,2),
    total_gst    DECIMAL(10,2),
    grand_total  DECIMAL(10,2),
    FOREIGN KEY (cid) REFERENCES customers(cid)
);

-- Table 4: invoice_items -----------------------------------------------------
CREATE TABLE IF NOT EXISTS invoice_items (
    item_id   INT AUTO_INCREMENT PRIMARY KEY,
    inv_no    INT NOT NULL,
    pid       INT NOT NULL,
    qty       INT NOT NULL,
    rate      DECIMAL(10,2),
    gst_rate  INT,
    taxable   DECIMAL(10,2),
    gst_amt   DECIMAL(10,2),
    FOREIGN KEY (inv_no) REFERENCES invoices(inv_no),
    FOREIGN KEY (pid)    REFERENCES products(pid)
);

-- Default walk-in customer (customer ID 1) -----------------------------------
INSERT IGNORE INTO customers (cid, name) VALUES (1, 'Walk-in Customer');
