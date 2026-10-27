(function () {
  const parts = JSON.parse(document.getElementById("agg-parts").textContent);
  const n = v => { const x = parseInt(v, 10); return isNaN(x) ? 0 : x; };
  function read(level, sex) {
    const el = document.querySelector(`input[data-level="${level}"][data-sex="${sex}"]`);
    return el ? n(el.value) : 0;
  }
  function recalc() {
    const lv = {};
    document.querySelectorAll("[data-total-for]").forEach(td => {
      const k = td.dataset.totalFor, m = read(k, "m"), f = read(k, "f");
      lv[k] = [m, f]; td.textContent = m + f;
    });
    Object.entries(parts).forEach(([key, list]) => {
      let m = 0, f = 0; list.forEach(p => { m += lv[p][0]; f += lv[p][1]; });
      ["m", "f", "t"].forEach((s, i) => {
        const el = document.getElementById(`agg-${key}-${s}`);
        if (el) el.textContent = i === 0 ? m : i === 1 ? f : m + f;
      });
    });
  }
  document.querySelectorAll("input.enr").forEach(i => i.addEventListener("input", recalc));
  document.querySelectorAll("form[data-confirm]").forEach(f => f.addEventListener("submit", e => {
    if (!confirm(f.dataset.confirm)) e.preventDefault();
  }));
  recalc();
})();
