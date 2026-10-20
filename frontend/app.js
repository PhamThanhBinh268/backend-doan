/* ============================================================
   HAEIM_Damped — Dashboard (Vanilla JS, không phụ thuộc ngoài)
   ============================================================ */
const API = (() => {
  const saved = localStorage.getItem("haeim_api_base");
  return saved === null ? "" : saved;
})();

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtPat = (p) => "{" + p.join(",") + "}";
const nf = (n, d = 4) => (n === null || n === undefined || Number.isNaN(n) ? "—" : Number(n).toFixed(d));

/* ---------------------------------------------------------- console */
function log(msg, kind = "") {
  const el = $("console");
  const t = new Date().toLocaleTimeString("vi-VN");
  el.insertAdjacentHTML("beforeend",
    `<div><span class="t">${t}</span><span class="${kind ? "l-" + kind : ""}">${esc(msg)}</span></div>`);
  el.scrollTop = el.scrollHeight;
  while (el.children.length > 120) el.removeChild(el.firstChild);
}

/* ---------------------------------------------------------- api */
async function jget(p) {
  const r = await fetch(API + p);
  if (!r.ok) throw new Error(`${p} → ${r.status} ${(await r.text()).slice(0, 160)}`);
  return r.json();
}
async function jpost(p, body) {
  const r = await fetch(API + p, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${p} → ${r.status} ${(await r.text()).slice(0, 160)}`);
  return r.json();
}
function busy(btn, on) { if (btn) btn.disabled = on; }

/* ---------------------------------------------------------- tabs */
document.querySelectorAll(".tab").forEach((t) => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".page").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("page-" + t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "data") loadConfig();
  });
});

/* ---------------------------------------------------------- charts */
function barChart(el, items, opts = {}) {
  if (!items.length) { el.innerHTML = '<p class="muted">Không có dữ liệu.</p>'; return; }
  const W = 760, H = opts.height || 260, padL = 52, padR = 16, padT = 18, padB = 46;
  const maxV = Math.max(...items.map((d) => d.value), opts.min || 0) * 1.12 || 1;
  const iw = W - padL - padR, ih = H - padT - padB;
  const bw = Math.min(56, (iw / items.length) * 0.62);
  const gap = iw / items.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  // lưới ngang + nhãn trục Y
  for (let i = 0; i <= 4; i++) {
    const y = padT + ih - (ih * i) / 4;
    const v = (maxV * i) / 4;
    s += `<line class="grid-line" x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"/>`;
    s += `<text class="axis-text" x="${padL - 8}" y="${y + 3.5}" text-anchor="end">${v.toFixed(v < 1 ? 2 : 0)}</text>`;
  }
  s += `<line class="axis" x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + ih}"/>`;
  s += `<line class="axis" x1="${padL}" y1="${padT + ih}" x2="${W - padR}" y2="${padT + ih}"/>`;
  items.forEach((d, i) => {
    const h = (d.value / maxV) * ih;
    const x = padL + gap * i + (gap - bw) / 2;
    const y = padT + ih - h;
    const cls = opts.color ? d.color || opts.color : "bar";
    s += `<rect class="${cls}" x="${x}" y="${y}" width="${bw}" height="${Math.max(h, 1)}" rx="3"><title>${esc(d.label)}: ${d.value}</title></rect>`;
    if (d.value > 0) s += `<text class="bar-label" x="${x + bw / 2}" y="${y - 5}" text-anchor="middle">${nf(d.value, 3)}</text>`;
    s += `<text class="axis-text" x="${x + bw / 2}" y="${padT + ih + 16}" text-anchor="middle">${esc(d.label)}</text>`;
    if (d.sub) s += `<text class="axis-text" x="${x + bw / 2}" y="${padT + ih + 30}" text-anchor="middle">${esc(d.sub)}</text>`;
  });
  if (opts.threshold !== undefined) {
    const y = padT + ih - (opts.threshold / maxV) * ih;
    s += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#f85149" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    s += `<text class="axis-text" x="${W - padR}" y="${y - 5}" text-anchor="end" fill="#f85149">minae = ${opts.threshold}</text>`;
  }
  s += `<text class="axis-text" x="${padL}" y="${H - 8}">${esc(opts.xlabel || "")}</text></svg>`;
  el.innerHTML = s;
}

function lineChart(el, series, opts = {}) {
  if (!series.length || !series[0].points.length) { el.innerHTML = '<p class="muted">Không có dữ liệu.</p>'; return; }
  const W = 760, H = opts.height || 280, padL = 52, padR = 18, padT = 18, padB = 44;
  const xs = series[0].points.map((p) => p.x);
  const allY = series.flatMap((s) => s.points.map((p) => p.value));
  const minV = Math.min(0, ...allY), maxV = Math.max(...allY) * 1.15 || 1;
  const iw = W - padL - padR, ih = H - padT - padB;
  const xOf = (i) => padL + (xs.length === 1 ? iw / 2 : (iw * i) / (xs.length - 1));
  const yOf = (v) => padT + ih - ((v - minV) / (maxV - minV || 1)) * ih;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  for (let i = 0; i <= 4; i++) {
    const y = padT + ih - (ih * i) / 4;
    const v = minV + ((maxV - minV) * i) / 4;
    s += `<line class="grid-line" x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"/>`;
    s += `<text class="axis-text" x="${padL - 8}" y="${y + 3.5}" text-anchor="end">${v.toFixed(v < 10 ? 2 : 0)}</text>`;
  }
  s += `<line class="axis" x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + ih}"/>`;
  s += `<line class="axis" x1="${padL}" y1="${padT + ih}" x2="${W - padR}" y2="${padT + ih}"/>`;
  xs.forEach((x, i) => {
    s += `<text class="axis-text" x="${xOf(i)}" y="${padT + ih + 16}" text-anchor="middle">${esc(x)}</text>`;
  });
  series.forEach((ser) => {
    const pts = ser.points.map((p, i) => `${xOf(i)},${yOf(p.value)}`).join(" ");
    s += `<polyline class="line ${ser.cls || ""}" points="${pts}"/>`;
    ser.points.forEach((p, i) => {
      s += `<circle class="point" cx="${xOf(i)}" cy="${yOf(p.value)}" r="3.5" stroke="${ser.stroke || "var(--accent)"}"><title>${esc(ser.name)} @ ${esc(p.x)}: ${p.value}</title></circle>`;
    });
  });
  s += `<text class="axis-text" x="${padL}" y="${H - 8}">${esc(opts.xlabel || "")}</text></svg>`;
  el.innerHTML = s +
    `<div class="legend">${series.map((se) =>
      `<span><i style="background:${se.stroke || "var(--accent)"}"></i>${esc(se.name)}</span>`).join("")}</div>`;
}

/* ---------------------------------------------------------- tổng quan */
let lastMine = null;
async function loadStatus() {
  try {
    const s = await jget("/");
    $("hdrStats").innerHTML =
      `Ltid <b>${s.ltid}</b> · <b>${s.transactions}</b> GD · <b>${s.items}</b> mục · v<b>${s.version}</b>`;
    $("kpis").innerHTML = `
      ${kpi("Giao dịch", s.transactions, `Ltid = ${s.ltid}`)}
      ${kpi("Mục khác nhau", s.items, "số mục trong bảng EU/INV")}
      ${kpi("Kết quả DHAEIs", lastMine ? lastMine.dhaeis.length : "—", "lần khai thác gần nhất")}
      ${kpi("Thời gian khai thác", lastMine ? lastMine.stats.elapsed_ms + " ms" : "—", "Pha 2 + Pha 3", "ok")}
      ${kpi("Phép ghép", lastMine ? `${lastMine.stats.join_success}/${lastMine.stats.join_attempts}` : "—", "thành công / thử")}
      ${kpi("Cắt tỉa", lastMine ? lastMine.stats.pruned_stdaeub : "—", "nhánh bị cắt", "warn")}`;
    $("mConstruction").textContent = `${s.transactions} giao dịch · ${s.items} mục trong DAE-List`;
    if (lastMine) {
      $("mRestructure").textContent = `${lastMine.candidates.length} ứng viên · order [${lastMine.order.join(", ")}]`;
      $("mExpansion").textContent = `${lastMine.dhaeis.length} HAEI · ${lastMine.stats.join_success} phép ghép`;
    }
  } catch (e) { log("LỖI trạng thái: " + e.message, "err"); }
}
function kpi(label, value, sub, cls = "") {
  return `<div class="kpi ${cls}"><div class="kpi-label">${esc(label)}</div>
          <div class="kpi-value">${esc(value)}</div><div class="kpi-sub">${esc(sub || "")}</div></div>`;
}

/* ---------------------------------------------------------- kiểm chứng nhanh */
$("btnQuickValidate")?.addEventListener("click", async () => {
  const btn = $("btnQuickValidate"); busy(btn, true);
  try {
    const r = await jpost("/api/validate", {
      f: parseFloat($("q_f").value), minae: parseFloat($("q_minae").value),
    });
    const ok = r.sound && r.agreement === 1;
    $("quickValidate").innerHTML = `
      <div class="stat-grid">
        ${kpi("Kết quả thuật toán", r.pruned.count, "HAEI tìm được")}
        ${kpi("Ground truth", r.exact.count, "duyệt tất cả tập mục")}
        ${kpi("Tỉ lệ khớp", (r.agreement * 100).toFixed(1) + "%", "agreement", ok ? "ok" : "bad")}
        ${kpi("Tốc độ", (r.speedup || 0) + "×", "nhanh hơn ground truth")}
      </div>
      <div class="note ${ok ? "ok" : "bad"}">
        ${ok ? "✔ Khớp 100% — phép cắt tỉa <b>an toàn</b>, không bỏ sót HAEI nào."
             : "✘ Có sai lệch: bỏ sót " + (r.missing || []).length + " / sinh thừa " + (r.extra || []).length}
      </div>
      <div class="muted small">Ground truth duyệt ${r.exact.itemsets_examined.toLocaleString("vi-VN")} tập mục trong ${r.exact.elapsed_ms} ms.</div>`;
    log(`Kiểm chứng: ${r.pruned.count}/${r.exact.count} HAEI, khớp ${(r.agreement * 100).toFixed(1)}%`, ok ? "ok" : "err");
  } catch (e) { log("LỖI kiểm chứng: " + e.message, "err"); }
  busy(btn, false);
});

/* ---------------------------------------------------------- dữ liệu */
async function loadDatasets() {
  try {
    const d = await jget("/api/datasets");
    $("dsKey").innerHTML = d.datasets.map((x) =>
      `<option value="${x.key}">${esc(x.name)} — ${x.transactions} GD / ${x.items} mục</option>`).join("");
  } catch (e) { log("LỖI datasets: " + e.message, "err"); }
}
$("btnLoadDataset")?.addEventListener("click", async () => {
  const btn = $("btnLoadDataset"); busy(btn, true);
  try {
    const r = await jpost("/api/dataset/load", { key: $("dsKey").value });
    log(`Đã nạp bộ dữ liệu ${$("dsKey").value}: ${r.loaded} GD`, "ok");
    $("dsInfo").innerHTML = `<div class="note ok">Đã nạp <b>${r.loaded}</b> giao dịch (Ltid=${r.ltid}). ${esc(r.dataset.description || "")}</div>`;
    await refreshData();
  } catch (e) { log("LỖI nạp dữ liệu: " + e.message, "err"); }
  busy(btn, false);
});
$("btnGenerate")?.addEventListener("click", async () => {
  const btn = $("btnGenerate"); busy(btn, true);
  try {
    const r = await jpost("/api/dataset/generate", {
      n_transactions: +$("genNtx").value, n_items: +$("genNitems").value,
      seed: +$("genSeed").value, max_items_per_tx: +$("genMaxb").value, load: true,
    });
    log(`Đã sinh ${r.loaded} GD / ${r.dataset.items} mục (seed ${$("genSeed").value})`, "ok");
    $("dsInfo").innerHTML = `<div class="note ok">Đã sinh &amp; nạp <b>${r.loaded}</b> giao dịch — ${esc(r.dataset.description)}</div>`;
    await refreshData();
  } catch (e) { log("LỖI sinh dữ liệu: " + e.message, "err"); }
  busy(btn, false);
});
$("btnImportCsv")?.addEventListener("click", async () => {
  const btn = $("btnImportCsv"); busy(btn, true);
  try {
    const r = await jpost("/api/dataset/import", { csv: $("csvText").value, load: true });
    log(`Đã nhập CSV: ${r.transactions} GD / ${r.items} mục`, "ok");
    $("dsInfo").innerHTML = `<div class="note ok">Đã nhập <b>${r.transactions}</b> giao dịch, <b>${r.items}</b> mục (EU/INV suy ra tự động).</div>`;
    await refreshData();
  } catch (e) { log("LỖI nhập CSV: " + e.message, "err"); }
  busy(btn, false);
});
$("btnReset")?.addEventListener("click", async () => {
  try { await jpost("/api/reset", {}); log("Đã xóa luồng", "warn"); await refreshData(); }
  catch (e) { log("LỖI reset: " + e.message, "err"); }
});
$("btnLoadExample")?.addEventListener("click", async () => {
  try { const r = await jpost("/api/load-example", {}); log(`Đã nạp Bảng 1 của PDF (${r.loaded} GD)`, "ok"); await refreshData(); }
  catch (e) { log("LỖI load-example: " + e.message, "err"); }
});
$("btnAddTx")?.addEventListener("click", async () => {
  try {
    const items = $("newItems").value.split(",").map((x) => x.trim()).filter(Boolean).map((p) => {
      const [item, qty] = p.split(":").map((x) => x.trim());
      if (!item || !qty) throw new Error("Sai định dạng (vd a:1,b:2)");
      return { item, qty: Number(qty) };
    });
    const r = await jpost("/api/transactions", { items });
    log(`Đã thêm T_${r.tid} (Construction)`, "ok");
    await refreshData();
  } catch (e) { log("LỖI thêm giao dịch: " + e.message, "err"); }
});

async function loadConfig() {
  try {
    const c = await jget("/api/config");
    const keys = Object.keys(c.eu).sort();
    $("configTable").innerHTML = `<table><thead><tr><th>mục</th><th class="num">eu</th>
      <th class="num">cu</th><th class="num">inv</th></tr></thead><tbody>` +
      keys.map((k) => `<tr><td class="mono">${esc(k)}</td><td class="num">${c.eu[k]}</td>
        <td class="num">${c.cu[k] ?? "—"}</td><td class="num">${c.inv[k]}</td></tr>`).join("") + "</tbody></table>";
  } catch (e) { log("LỖI config: " + e.message, "err"); }
}
async function loadTx() {
  try {
    const d = await jget("/api/transactions");
    $("txCount").textContent = `${d.transactions.length} giao dịch · Ltid=${d.ltid}`;
    const rows = d.transactions.map((t) =>
      `<tr><td class="mono">${t.tid}</td><td class="mono">${t.items.map((x) => esc(x.item + ":" + x.qty)).join(", ")}</td></tr>`).join("");
    $("txTable").innerHTML = `<table><thead><tr><th>tid</th><th>items (item:qty)</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (e) { log("LỖI transactions: " + e.message, "err"); }
}
async function refreshData() { await loadStatus(); await loadConfig(); await loadTx(); }

/* ---------------------------------------------------------- khai thác */
$("btnMine")?.addEventListener("click", async () => {
  const btn = $("btnMine"); busy(btn, true);
  try {
    const r = await jpost("/api/mine", {
      f: parseFloat($("m_f").value), minae: parseFloat($("m_minae").value),
      sound: $("m_sound").checked,
    });
    lastMine = r;
    renderMine(r);
    await loadStatus();
    log(`Khai thác: ${r.dhaeis.length} HAEI (${r.stats.elapsed_ms} ms${r.cached ? ", cache" : ""})`, "ok");
  } catch (e) { log("LỖI khai thác: " + e.message, "err"); }
  busy(btn, false);
});

function renderMine(r) {
  const minae = r.minae;
  $("mineSummary").innerHTML = `
    <div class="stat-grid">
      ${kpi("DHAEIs", r.dhaeis.length, "tập kết quả", "ok")}
      ${kpi("Ứng viên", r.candidates.length, "qua bộ lọc Restructure")}
      ${kpi("Thời gian", r.stats.elapsed_ms + " ms", "Pha 2 + Pha 3")}
      ${kpi("Phép ghép", `${r.stats.join_success}/${r.stats.join_attempts}`, "thành công / thử")}
      ${kpi("Nhánh bị cắt", r.stats.pruned_stdaeub, "cắt tỉa an toàn", "warn")}
    </div>
    <div class="note">Thứ tự sau Restructure (tăng dần SMDAEUB):
      <b class="mono">[${r.order.map(esc).join(", ")}]</b> · Ltid = <b>${r.ltid}</b> · f = <b>${r.f}</b> · minae = <b>${minae}</b>
      · chế độ cắt tỉa: <b>${$("m_sound").checked ? "âm (an toàn — khớp 100% ground truth)" : "kiểu PDF (nhanh hơn, có thể bỏ sót HAEI)"}</b></div>`;

  $("dhaeiTable").innerHTML = `<table><thead><tr><th>pattern</th><th class="num">Sdae</th>
    <th class="num">SMDAEUB</th><th class="num">STDAEUB</th><th>kết luận</th></tr></thead><tbody>` +
    r.dhaeis.map((d) => `<tr><td class="mono">${fmtPat(d.pattern.map(esc))}</td>
      <td class="num">${d.sdae}</td><td class="num">${d.smdaeub}</td><td class="num">${d.stdaeub}</td>
      <td><span class="badge ok">HAEI</span></td></tr>`).join("") + "</tbody></table>";

  $("candTable").innerHTML = `<table><thead><tr><th>pattern</th><th class="num">Sdae</th>
    <th class="num">SMDAEUB</th><th class="num">STDAEUB</th><th>trạng thái</th></tr></thead><tbody>` +
    r.candidates.map((c) => {
      const haei = c.sdae >= minae;
      const ext = c.stdaeub >= minae;
      return `<tr><td class="mono">${fmtPat(c.pattern.map(esc))}</td>
        <td class="num">${c.sdae}</td><td class="num">${c.smdaeub}</td><td class="num">${c.stdaeub}</td>
        <td>${haei ? '<span class="badge ok">HAEI</span>' : '<span class="badge">loại</span>'}
            ${ext ? '<span class="badge info">mở rộng</span>' : '<span class="badge warn">cắt</span>'}</td></tr>`;
    }).join("") + "</tbody></table>";

  barChart($("orderChart"), r.candidates.map((c) => ({
    label: fmtPat(c.pattern), value: c.smdaeub,
    sub: c.sdae >= minae ? "HAEI" : "loại",
    color: c.sdae >= minae ? "bar ok" : "bar alt",
  })), { xlabel: "Số lượng HAEI", threshold: minae, height: 240 });

  barChart($("chartSdae"), r.dhaeis.map((d) => ({
    label: fmtPat(d.pattern), value: d.sdae, color: "bar ok",
  })), { xlabel: "Sdae của tập HAEI", threshold: minae, height: 240 });
}

/* ---------------------------------------------------------- DAE-List */
$("btnLoadDae")?.addEventListener("click", async () => {
  try {
    const r = await jget("/api/dae-lists");
    $("daeOrder").textContent = "order: [" + r.order.join(", ") + "]"
      + (r.sound_mode ? "  ·  chế độ: cắt tỉa âm (an toàn)" : "  ·  chế độ: kiểu PDF (có thể bỏ sót)");
    $("daeList").innerHTML = r.nodes.map((n) => `
      <div class="dae-node">
        <div class="dae-head">
          <span class="pat">${fmtPat(n.pattern.map(esc))}</span>
          <span class="m">Inv <b>${n.inv}</b></span>
          <span class="m">Sdae <b>${n.sdae}</b></span>
          <span class="m">SMDAEUB <b>${n.smdaeub}</b></span>
          <span class="m">STDAEUB <b>${n.stdaeub}</b></span>
          <span class="m">cận âm <b>${nf(n.sound_bound, 4)}</b></span>
        </div>
        <table><thead><tr><th>tid</th><th class="num">u</th><th class="num">ae</th><th class="num">MAEUB</th>
          <th class="num">dae</th><th class="num">MDAEUB</th><th class="num">TDAEUB</th>
          <th class="num">maxru</th><th class="num">minInv</th><th class="num">k</th></tr></thead><tbody>
          ${n.entries.map((e) => `<tr><td>${e.tid}</td><td class="num">${e.u}</td><td class="num">${e.ae}</td>
            <td class="num">${e.maeub}</td><td class="num">${e.dae}</td><td class="num">${e.mdaeub}</td>
            <td class="num">${e.tdaeub}</td><td class="num">${e.maxru}</td><td class="num">${e.minInv}</td>
            <td class="num">${e.k}</td></tr>`).join("")}
        </tbody></table>
      </div>`).join("");
    log(`Đã tải ${r.nodes.length} node DAE-List`, "ok");
  } catch (e) { log("LỖI DAE-List: " + e.message, "err"); }
});

/* ---------------------------------------------------------- thực nghiệm */
$("btnBench")?.addEventListener("click", async () => {
  const btn = $("btnBench"); busy(btn, true);
  try {
    const r = await jpost("/api/bench", {
      n_transactions: +$("bNtx").value, n_items: +$("bNitems").value,
      max_items_per_tx: +$("bMaxb").value, seed: +$("bSeed").value,
      f: 0.8, minae: 0.2, with_exact: true,
    });
    const ok = r.sound;
    $("benchOut").innerHTML = `
      <div class="stat-grid">
        ${kpi("Thời gian (cắt tỉa)", r.pruned_ms + " ms", "HAEIM_Damped")}
        ${kpi("Thời gian (ground truth)", (r.exact_ms ?? "—") + " ms", "duyệt tất cả tập mục")}
        ${kpi("Nhanh hơn", (r.speedup ?? "—") + "×", "hệ số")}
        ${kpi("Tập mục đã duyệt", (r.itemsets_examined ?? "—").toLocaleString("vi-VN"), "ground truth")}
        ${kpi("Tỉ lệ khớp", ((r.agreement ?? 0) * 100).toFixed(1) + "%", ok ? "an toàn" : "bỏ sót", ok ? "ok" : "bad")}
      </div>
      <div class="note ${ok ? "ok" : "bad"}">${ok
        ? "✔ Kết quả khớp 100% ground truth — cắt tỉa không bỏ sót HAEI."
        : "✘ Có sai lệch."}</div>
      ${r.exact_skipped ? `<div class="note warn">Ground truth bị bỏ qua: ${esc(r.exact_skipped)}</div>` : ""}`;
    log(`Benchmark ${r.transactions}×${r.items}: ${r.pruned_ms}ms vs ${r.exact_ms}ms (${r.speedup}×)`, "ok");
  } catch (e) { log("LỖI benchmark: " + e.message, "err"); }
  busy(btn, false);
});

$("btnPruneCmp")?.addEventListener("click", async () => {
  const btn = $("btnPruneCmp"); busy(btn, true);
  try {
    const r = await jpost("/api/pruning-comparison", {
      n_transactions: +$("pNtx").value, n_items: +$("pNitems").value,
      max_items_per_tx: +$("pMaxb").value,
    });
    const s = r.rows.find((x) => x.strategy === "sound");
    const l = r.rows.find((x) => x.strategy === "legacy");
    $("pruneCmpOut").innerHTML = `
      <div class="stat-grid">
        ${kpi("Cắt tỉa âm", s.elapsed_ms + " ms", s.hits + "/" + s.exact_hits + " HAEI", "ok")}
        ${kpi("Cắt tỉa bản PDF", l.elapsed_ms + " ms", l.hits + "/" + l.exact_hits + " HAEI", l.sound ? "ok" : "bad")}
        ${kpi("HAEI bị bỏ sót", r.missed_by_legacy, "bởi bản PDF", r.missed_by_legacy ? "bad" : "ok")}
        ${kpi("Nhanh hơn ground truth", (r.speedup_sound_vs_exact ?? "—") + "×", "bản âm", "ok")}
        ${kpi("Ground truth", r.exact_ms + " ms", r.itemsets_examined.toLocaleString("vi-VN") + " tập mục")}
      </div>
      <div class="note ok"><b>Bản âm</b>: khớp 100% ground truth (${s.agreement * 100}%) — không bỏ sót HAEI nào.</div>
      ${l.missing.length ? `<div class="note bad"><b>Bản PDF (1-phần-mở-rộng)</b> bỏ sót ${l.missing.length} HAEI:
        ${l.missing.map((p) => `<span class="mono">${fmtPat(p.map(esc))}</span>`).join(", ")}
        — do cận trên vi phạm với phần mở rộng ≥ 2 mục.</div>` : ""}
      <div id="pruneChart"></div>`;
    barChart($("pruneChart"), [
      { label: "cắt tỉa âm", value: s.elapsed_ms, color: "bar ok", sub: s.hits + " HAEI" },
      { label: "bản PDF", value: l.elapsed_ms, color: "bar alt", sub: l.hits + " HAEI" },
      { label: "ground truth", value: r.exact_ms, color: "bar", sub: r.exact_hits + " HAEI" },
    ], { xlabel: "Thời gian (ms) — càng thấp càng tốt", height: 250 });
    log(`So sánh cắt tỉa: âm ${s.elapsed_ms}ms (${s.hits} HAEI) vs PDF ${l.elapsed_ms}ms (${l.hits} HAEI)`, "ok");
  } catch (e) { log("LỖI so sánh cắt tỉa: " + e.message, "err"); }
  busy(btn, false);
});

$("btnScalability")?.addEventListener("click", async () => {
  const btn = $("btnScalability"); busy(btn, true);
  try {
    const r = await jpost("/api/scalability", { f: 0.8, minae: 0.2, with_exact: true });
    $("scaleOut").innerHTML = `<div id="scaleChart"></div>
      <table><thead><tr><th>cấu hình</th><th class="num">cắt tỉa (ms)</th><th class="num">ground truth (ms)</th>
      <th class="num">nhanh hơn</th><th class="num">HAEI</th><th class="num">khớp</th></tr></thead><tbody>` +
      r.rows.map((x) => `<tr><td>${x.transactions} GD / ${x.items} mục</td>
        <td class="num">${x.pruned_ms}</td><td class="num">${x.exact_ms ?? "—"}</td>
        <td class="num">${x.speedup ?? "—"}×</td><td class="num">${x.pruned_hits}</td>
        <td class="num">${((x.agreement ?? 0) * 100).toFixed(0)}%</td></tr>`).join("") + "</tbody></table>";
    lineChart($("scaleChart"), [
      { name: "HAEIM_Damped (cắt tỉa âm)", stroke: "var(--accent)", cls: "",
        points: r.rows.map((x) => ({ x: `${x.transactions}GD`, value: x.pruned_ms })) },
      { name: "Ground truth (duyệt tất cả)", stroke: "var(--accent-2)", cls: "alt",
        points: r.rows.map((x) => ({ x: `${x.transactions}GD`, value: x.exact_ms ?? 0 })) },
    ], { xlabel: "Số giao dịch", height: 260 });
    log("Đã quét scalability", "ok");
  } catch (e) { log("LỖI scalability: " + e.message, "err"); }
  busy(btn, false);
});

$("btnSweep")?.addEventListener("click", async () => {
  const btn = $("btnSweep"); busy(btn, true);
  try {
    const r = await jpost("/api/sweep", {});
    $("sweepOut").innerHTML = `<div id="sweepChart"></div>
      <table><thead><tr><th>f</th><th class="num">minae</th><th class="num">#HAEI</th>
      <th class="num">Sdae TB</th><th class="num">Sdae max</th></tr></thead><tbody>` +
      r.rows.map((x) => `<tr><td>${x.f}</td><td class="num">${x.minae}</td><td class="num">${x.count}</td>
        <td class="num">${x.mean_sdae}</td><td class="num">${x.max_sdae}</td></tr>`).join("") + "</tbody></table>";
    const byF = r.f_values.map((f) => ({
      name: `f=${f}`, stroke: "var(--accent)",
      points: r.rows.filter((x) => x.f === f).map((x) => ({ x: String(x.minae), value: x.count })),
    }));
    lineChart($("sweepChart"), byF, { xlabel: "Ngưỡng minae", height: 260 });
    log("Đã quét tham số f/minae", "ok");
  } catch (e) { log("LỖI sweep: " + e.message, "err"); }
  busy(btn, false);
});

$("btnCost")?.addEventListener("click", async () => {
  const btn = $("btnCost"); busy(btn, true);
  try {
    const r = await jpost("/api/construction-cost", {
      n_transactions: +$("bNtx").value, n_items: +$("bNitems").value, seed: +$("bSeed").value });
    const ok = r.growth_ratio !== null && r.growth_ratio < 3;
    $("costOut").innerHTML = `
      <div class="stat-grid">
        ${kpi("Tổng thời gian", r.total_ms + " ms", r.transactions + " giao dịch")}
        ${kpi("TB nửa đầu", r.avg_ms_first_half + " ms", "mỗi giao dịch")}
        ${kpi("TB nửa sau", r.avg_ms_second_half + " ms", "mỗi giao dịch")}
        ${kpi("Hệ số phình to", r.growth_ratio, "~1 nghĩa là O(|T_j|)", ok ? "ok" : "warn")}
        ${kpi("Nạp hàng loạt", r.bulk_ms + " ms", "1 request nhiều T_j")}
      </div>
      <div class="note ${ok ? "ok" : "warn"}">${ok
        ? "✔ Thời gian xử lý mỗi giao dịch không phình theo độ dài luồng → Pha 1 đúng O(|T_j|), không quét lại dữ liệu cũ."
        : "⚠ Hệ số phình to lớn — cần kiểm tra lại."}</div>`;
    log(`Chi phí Construction: growth=${r.growth_ratio}`, ok ? "ok" : "warn");
  } catch (e) { log("LỖI đo chi phí: " + e.message, "err"); }
  busy(btn, false);
});

/* ---------------------------------------------------------- giải thích */
$("btnExplain")?.addEventListener("click", async () => {
  try {
    const pat = $("exPattern").value.split(",").map((x) => x.trim()).filter(Boolean);
    const r = await jget(`/api/explain?pattern=${encodeURIComponent(pat.join(","))}&f=${$("exF").value}&minae=${$("exMinae").value}`);
    renderExplain(r);
  } catch (e) { log("LỖI giải thích: " + e.message, "err"); }
});
$("btnExplainAll")?.addEventListener("click", async () => {
  try {
    const r = await jget(`/api/explain/all?f=${$("exF").value}&minae=${$("exMinae").value}`);
    $("explainOut").innerHTML = r.items.map((it) => explainBlock(it)).join("");
  } catch (e) { log("LỖI giải thích: " + e.message, "err"); }
});

function renderExplain(r) {
  $("explainOut").innerHTML = explainBlock(r);
}
function explainBlock(r) {
  return `
    <div class="stat-grid">
      ${kpi("Pattern", fmtPat(r.pattern), r.size + " mục")}
      ${kpi("Sdae", nf(r.sdae), "ngưỡng " + r.minae, r.is_haei ? "ok" : "bad")}
      ${kpi("SMDAEUB", nf(r.smdaeub), "cận trên PDF")}
      ${kpi("STDAEUB", nf(r.stdaeub), "cận trên 1-phần-mở-rộng")}
      ${kpi("Giao dịch chứa mẫu", r.transactions_covered, "đóng góp vào Sdae")}
    </div>
    <div class="note ${r.is_haei ? "ok" : "bad"}">${r.is_haei
      ? `✔ <b>HAEI</b> — Sdae = ${nf(r.sdae)} ≥ minae = ${r.minae} (biên ${nf(r.margin)}).`
      : `✘ Không phải HAEI — Sdae = ${nf(r.sdae)} &lt; minae = ${r.minae}.`}</div>
    <h3 class="small">Lý do (truy vết 3 pha)</h3>
    ${r.reasons.map((x) => `<div class="reason"><span class="ph">${esc(x.phase)}</span>
      <span class="tx">${esc(x.message)}</span></div>`).join("")}
    <h3 class="small">Đóng góp theo giao dịch</h3>
    <table><thead><tr><th>tid</th><th>qty</th><th class="num">u</th><th class="num">ae</th>
      <th class="num">w=f^(L−t)</th><th class="num">dae</th><th class="num">maxru</th>
      <th class="num">minInv</th><th class="num">k</th></tr></thead><tbody>
      ${r.entries.map((e) => `<tr><td>${e.tid}</td><td class="mono">${esc(JSON.stringify(e.qty))}</td>
        <td class="num">${e.u}</td><td class="num">${e.ae}</td><td class="num">${e.w}</td>
        <td class="num">${e.dae}</td><td class="num">${e.maxru ?? "—"}</td>
        <td class="num">${e.min_inv ?? "—"}</td><td class="num">${e.k ?? "—"}</td></tr>`).join("")}
    </tbody></table>`;
}

/* ---------------------------------------------------------- khởi động */
$("apiBase").value = API;
$("apiBase").addEventListener("change", (e) => {
  localStorage.setItem("haeim_api_base", e.target.value);
  log("Đã đổi API base: " + (e.target.value || "(cùng origin)"), "warn");
  refreshData();
});

loadDatasets();
refreshData();
log("Sẵn sàng. Mặc định: luồng Bảng 1 của PDF (8 giao dịch).");
