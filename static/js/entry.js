
(function () {
  "use strict";

  const partsElement = document.getElementById("agg-parts");

  let parts = {};

  // Read enrollment aggregate definitions when available.
  if (partsElement) {
    try {
      parts = JSON.parse(partsElement.textContent);
    } catch (error) {
      console.error(
        "Unable to read enrollment aggregate definitions.",
        error
      );
    }
  }

  function numberValue(value) {
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) || parsed < 0 ? 0 : parsed;
  }

  // --------------------------------------------------
  // ENROLLMENT TOTALS
  // --------------------------------------------------

  function readEnrollment(level, sex) {
    const input = document.querySelector(
      `input[data-level="${level}"][data-sex="${sex}"]`
    );

    return input ? numberValue(input.value) : 0;
  }

  function recalculateEnrollment() {
    const levels = {};

    document.querySelectorAll("[data-total-for]").forEach((cell) => {
      const level = cell.dataset.totalFor;
      const male = readEnrollment(level, "m");
      const female = readEnrollment(level, "f");

      levels[level] = [male, female];
      cell.textContent = male + female;
    });

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

  // --------------------------------------------------
  // SF4 MOVEMENT TOTALS
  // --------------------------------------------------

  function readMovement(category, period, sex) {
    const input = document.querySelector(
      `input[name="${category}_${period}_${sex}"]`
    );

    return input ? numberValue(input.value) : 0;
  }

  function setMovementCell(id, value) {
    const cell = document.getElementById(id);

    if (cell) {
      cell.textContent = value;
    }
  }

  function recalculateMovements() {
    const categories = [
      "dropout",
      "transferred_out",
      "transferred_in"
    ];

    categories.forEach((category) => {
      // A: Cumulative as of Previous Month
      const previousMale = readMovement(category, "previous", "male");
      const previousFemale = readMovement(category, "previous", "female");
      const previousTotal = previousMale + previousFemale;

      setMovementCell(
        `movement-${category}-previous-total`,
        previousTotal
      );

      // B: For the Month
      const monthlyMale = readMovement(category, "monthly", "male");
      const monthlyFemale = readMovement(category, "monthly", "female");
      const monthlyTotal = monthlyMale + monthlyFemale;

      setMovementCell(
        `movement-${category}-monthly-total`,
        monthlyTotal
      );

      // A+B: Cumulative as of End of the Month
      const cumulativeMale = previousMale + monthlyMale;
      const cumulativeFemale = previousFemale + monthlyFemale;
      const cumulativeTotal = cumulativeMale + cumulativeFemale;

      setMovementCell(
        `movement-${category}-cumulative-male`,
        cumulativeMale
      );

      setMovementCell(
        `movement-${category}-cumulative-female`,
        cumulativeFemale
      );

      setMovementCell(
        `movement-${category}-cumulative-total`,
        cumulativeTotal
      );
    });
  }

  // --------------------------------------------------
  // EVENT LISTENERS
  // --------------------------------------------------

  document.querySelectorAll("input.enr").forEach((input) => {
    input.addEventListener("input", recalculateEnrollment);
  });

  document.querySelectorAll("input.movement-input").forEach((input) => {
    input.addEventListener("input", recalculateMovements);
  });

  // Keep confirmation dialogs for forms that request them.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Calculate initial values when the page loads.
  recalculateEnrollment();
  recalculateMovements();
})();
