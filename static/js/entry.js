(function () {
  "use strict";

  const partsElement = document.getElementById("agg-parts");

  // This script may also be loaded on a page without enrollment totals.
  if (!partsElement) {
    return;
  }

  let parts;

  try {
    parts = JSON.parse(partsElement.textContent);
  } catch (error) {
    console.error("Unable to read enrollment aggregate definitions.", error);
    return;
  }

  function numberValue(value) {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) || parsed < 0 ? 0 : parsed;
  }

  function read(level, sex) {
    const input = document.querySelector(
      `input[data-level="${level}"][data-sex="${sex}"]`
    );

    return input ? numberValue(input.value) : 0;
  }

  function recalculate() {
    const levels = {};

    // Calculate totals for the enrollment levels displayed on this page.
    document.querySelectorAll("[data-total-for]").forEach((cell) => {
      const level = cell.dataset.totalFor;
      const male = read(level, "m");
      const female = read(level, "f");

      levels[level] = [male, female];
      cell.textContent = male + female;
    });

    // Calculate aggregates safely, including when a level is not displayed.
    Object.entries(parts).forEach(([key, levelKeys]) => {
      let male = 0;
      let female = 0;

      levelKeys.forEach((levelKey) => {
        const values = levels[levelKey] || [0, 0];

        male += values[0];
        female += values[1];
      });

      const maleCell = document.getElementById(`agg-${key}-m`);
      const femaleCell = document.getElementById(`agg-${key}-f`);
      const totalCell = document.getElementById(`agg-${key}-t`);

      if (maleCell) maleCell.textContent = male;
      if (femaleCell) femaleCell.textContent = female;
      if (totalCell) totalCell.textContent = male + female;
    });
  }

  // Recalculate whenever an enrollment value changes.
  document.querySelectorAll("input.enr").forEach((input) => {
    input.addEventListener("input", recalculate);
  });

  // Preserve confirmation dialogs for forms that request them.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  recalculate();
})();