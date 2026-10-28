
(function () {
  "use strict";

  const partsElement = document.getElementById("agg-parts");
  let parts = {};

  // --------------------------------------------------
  // ENROLLMENT AGGREGATE DEFINITIONS
  // --------------------------------------------------

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
  // Existing enrollment behavior is preserved.
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

      if (maleCell) {
        maleCell.textContent = male;
      }

      if (femaleCell) {
        femaleCell.textContent = female;
      }

      if (totalCell) {
        totalCell.textContent = male + female;
      }
    });
  }

  // --------------------------------------------------
  // SF4 MOVEMENT — PER GRADE LEVEL AND CATEGORY
  // --------------------------------------------------

  function readMovement(level, category, period, sex) {
    const input = document.querySelector(
      `input.movement-input` +
      `[data-level="${level}"]` +
      `[data-category="${category}"]` +
      `[data-period="${period}"]` +
      `[data-sex="${sex}"]`
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
    const inputs = document.querySelectorAll(
      "input.movement-input[data-level][data-category]"
    );

    const pairs = new Set();

    inputs.forEach((input) => {
      const level = input.dataset.level;
      const category = input.dataset.category;

      if (level && category) {
        pairs.add(`${level}|${category}`);
      }
    });

    pairs.forEach((pair) => {
      const separator = pair.indexOf("|");
      const level = pair.slice(0, separator);
      const category = pair.slice(separator + 1);
      const key = `${level}-${category}`;

      // A — Cumulative as of Previous Month
      const previousMale = readMovement(
        level,
        category,
        "previous",
        "male"
      );

      const previousFemale = readMovement(
        level,
        category,
        "previous",
        "female"
      );

      setMovementCell(
        `movement-${key}-previous-total`,
        previousMale + previousFemale
      );

      // B — For the Month
      const monthlyMale = readMovement(
        level,
        category,
        "monthly",
        "male"
      );

      const monthlyFemale = readMovement(
        level,
        category,
        "monthly",
        "female"
      );

      setMovementCell(
        `movement-${key}-monthly-total`,
        monthlyMale + monthlyFemale
      );

      // A+B — Cumulative as of End of the Month
      const cumulativeMale = previousMale + monthlyMale;
      const cumulativeFemale = previousFemale + monthlyFemale;
      const cumulativeTotal = cumulativeMale + cumulativeFemale;

      setMovementCell(
        `movement-${key}-cumulative-male`,
        cumulativeMale
      );

      setMovementCell(
        `movement-${key}-cumulative-female`,
        cumulativeFemale
      );

      setMovementCell(
        `movement-${key}-cumulative-total`,
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

  // Preserve confirmation dialogs on existing forms.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // --------------------------------------------------
  // INITIAL CALCULATIONS
  // --------------------------------------------------

  recalculateEnrollment();
  recalculateMovements();
})();
