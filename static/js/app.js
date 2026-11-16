/* SmartBill - front-end helpers.
   All money is calculated again by the Python server when an invoice is saved;
   the numbers shown here are only a live preview. */
(function () {
  "use strict";

  /* ---------- small utilities ---------- */
  function inr(paise) {                       // paise (integer) -> Indian format
    var negative = paise < 0;
    paise = Math.abs(paise);
    var whole = String(Math.floor(paise / 100));
    var frac = String(paise % 100).padStart(2, "0");
    if (whole.length > 3) {
      var tail = whole.slice(-3), head = whole.slice(0, -3), groups = [];
      while (head.length > 2) { groups.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) { groups.unshift(head); }
      whole = groups.join(",") + "," + tail;
    }
    return (negative ? "-" : "") + "\u20B9" + whole + "." + frac;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  /* ---------- confirm before delete, print button ---------- */
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) { event.preventDefault(); }
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-print]")) { window.print(); }
  });

  /* ---------- PWA service worker ---------- */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      var url = document.body.getAttribute("data-sw-url");
      if (url) { navigator.serviceWorker.register(url).catch(function () {}); }
    });
  }

  /* ---------- billing screen ---------- */
  var billForm = document.getElementById("bill-form");
  if (!billForm) { return; }

  var products = JSON.parse(document.getElementById("products-data").textContent);
  var prefill = JSON.parse(document.getElementById("prefill-data").textContent);
  var byId = {};
  products.forEach(function (p) { byId[p.pid] = p; });

  var grid = document.getElementById("product-grid");
  var searchBox = document.getElementById("product-search");
  var noProducts = document.getElementById("no-products");
  var linesBox = document.getElementById("cart-lines");
  var emptyMsg = document.getElementById("cart-empty");
  var saveBtn = document.getElementById("save-bill");
  var mobileBar = document.getElementById("mobile-bar");
  var cart = [];                               // [{pid, qty}] in the order added

  function findLine(pid) {
    for (var i = 0; i < cart.length; i++) { if (cart[i].pid === pid) { return cart[i]; } }
    return null;
  }

  function renderProducts() {
    var term = searchBox.value.trim().toLowerCase();
    grid.textContent = "";
    var shown = 0;
    products.forEach(function (p) {
      if (term && (p.name + " " + p.category).toLowerCase().indexOf(term) === -1) { return; }
      shown += 1;
      var tile = el("button", "product-tile");
      tile.type = "button";
      tile.disabled = p.stock <= 0;
      tile.appendChild(el("span", "pt-name", p.name));
      if (p.category) { tile.appendChild(el("span", "pt-cat", p.category)); }
      tile.appendChild(el("span", "pt-price", inr(Math.round(p.price * 100))));
      var meta = p.stock <= 0 ? "Out of stock" : "GST " + p.gst + "% \u00B7 " + p.stock + " in stock";
      var cls = "pt-meta" + (p.stock <= 0 ? " out" : (p.stock < 10 ? " low" : ""));
      tile.appendChild(el("span", cls, meta));
      tile.addEventListener("click", function () { addToCart(p.pid); });
      grid.appendChild(tile);
    });
    noProducts.classList.toggle("d-none", shown !== 0);
  }

  function addToCart(pid) {
    var p = byId[pid];
    var line = findLine(pid);
    if (!line) { cart.push({ pid: pid, qty: 0 }); line = findLine(pid); }
    if (line.qty >= p.stock) { window.alert("Only " + p.stock + " unit(s) of " + p.name + " in stock."); return; }
    line.qty += 1;
    renderCart();
  }

  function setQty(pid, value) {
    var p = byId[pid], line = findLine(pid);
    var qty = parseInt(value, 10);
    if (isNaN(qty) || qty < 1) { qty = 1; }
    if (qty > p.stock) { qty = p.stock; window.alert("Only " + p.stock + " unit(s) of " + p.name + " in stock."); }
    line.qty = qty;
    renderCart();
  }

  function removeLine(pid) {
    cart = cart.filter(function (l) { return l.pid !== pid; });
    renderCart();
  }

  function renderCart() {
    linesBox.textContent = "";
    var taxable = 0, gst = 0, items = 0;
    cart.forEach(function (line) {
      var p = byId[line.pid];
      var lineTaxable = Math.round(p.price * 100) * line.qty;      // paise
      var lineGst = Math.round(lineTaxable * p.gst / 100);
      taxable += lineTaxable; gst += lineGst; items += line.qty;

      var row = el("div", "cart-line");
      var top = el("div", "cl-top");
      var info = el("div");
      info.appendChild(el("div", "cl-name", p.name));
      info.appendChild(el("div", "cl-sub", inr(Math.round(p.price * 100)) + " \u00B7 GST " + p.gst + "%"));
      var remove = el("button", "btn btn-sm btn-outline-danger", "Remove");
      remove.type = "button";
      remove.addEventListener("click", function () { removeLine(line.pid); });
      top.appendChild(info); top.appendChild(remove);

      var bottom = el("div", "cl-bottom");
      var stepper = el("div", "qty-stepper");
      var minus = el("button", "btn btn-outline-sb", "\u2212"); minus.type = "button";
      minus.setAttribute("aria-label", "Decrease quantity");
      var plus = el("button", "btn btn-outline-sb", "+"); plus.type = "button";
      plus.setAttribute("aria-label", "Increase quantity");
      var qtyInput = el("input", "form-control");
      qtyInput.type = "number"; qtyInput.name = "qty"; qtyInput.min = "1"; qtyInput.max = String(p.stock);
      qtyInput.step = "1"; qtyInput.value = String(line.qty); qtyInput.inputMode = "numeric";
      qtyInput.setAttribute("aria-label", "Quantity of " + p.name);
      var pidInput = el("input"); pidInput.type = "hidden"; pidInput.name = "pid"; pidInput.value = String(line.pid);
      minus.addEventListener("click", function () { if (line.qty > 1) { setQty(line.pid, line.qty - 1); } else { removeLine(line.pid); } });
      plus.addEventListener("click", function () { setQty(line.pid, line.qty + 1); });
      qtyInput.addEventListener("change", function () { setQty(line.pid, qtyInput.value); });
      stepper.appendChild(minus); stepper.appendChild(qtyInput); stepper.appendChild(plus);
      bottom.appendChild(stepper);
      bottom.appendChild(el("div", "cl-total", inr(lineTaxable + lineGst)));

      row.appendChild(pidInput); row.appendChild(top); row.appendChild(bottom);
      linesBox.appendChild(row);
    });

    var cgst = Math.round(gst / 2), sgst = gst - cgst, grand = taxable + gst;
    document.getElementById("t-taxable").textContent = inr(taxable);
    document.getElementById("t-cgst").textContent = inr(cgst);
    document.getElementById("t-sgst").textContent = inr(sgst);
    document.getElementById("t-grand").textContent = inr(grand);
    emptyMsg.classList.toggle("d-none", cart.length > 0);
    saveBtn.disabled = cart.length === 0;
    mobileBar.classList.toggle("d-none", cart.length === 0);
    document.getElementById("mb-count").textContent = items + (items === 1 ? " item" : " items");
    document.getElementById("mb-total").textContent = inr(grand);
  }

  billForm.addEventListener("submit", function (event) {
    if (cart.length === 0) { event.preventDefault(); return; }
    saveBtn.disabled = true;                     // stop double submission
    saveBtn.textContent = "Saving...";
  });
  searchBox.addEventListener("input", renderProducts);
  searchBox.addEventListener("keydown", function (event) { if (event.key === "Enter") { event.preventDefault(); } });

  prefill.forEach(function (item) {              // restore lines after an error
    var p = byId[item.pid];
    if (p && p.stock > 0 && !findLine(item.pid)) {
      cart.push({ pid: item.pid, qty: Math.max(1, Math.min(item.qty, p.stock)) });
    }
  });
  renderProducts();
  renderCart();
})();
