// SPDX-License-Identifier: Apache-2.0

(function () {
  "use strict";

  // Application State
  let currentRecipe = null;
  let originalRecipe = null;
  const deleteHistory = [];

  // Drag and drop tracking
  let draggedItem = null;

  // DOM Elements
  const extractForm = document.getElementById("extract-form");
  const recipeUrlInput = document.getElementById("recipe-url");
  const extractBtn = document.getElementById("extract-btn");
  const btnSpinner = document.getElementById("btn-spinner");
  const btnText = document.getElementById("btn-text");
  const alertBox = document.getElementById("alert-box");
  const workspace = document.getElementById("recipe-workspace");

  const viewEditBtn = document.getElementById("view-edit-btn");
  const viewPreviewBtn = document.getElementById("view-preview-btn");
  const editorContainer = document.getElementById("editor-container");
  const previewContainer = document.getElementById("preview-container");

  const printBtn = document.getElementById("print-btn");
  const resetBtn = document.getElementById("reset-btn");
  const undoBtn = document.getElementById("undo-btn");

  // Unit toggle buttons
  const unitOrigBtn = document.getElementById("unit-orig-btn");
  const unitMetricBtn = document.getElementById("unit-metric-btn");
  const unitUkBtn = document.getElementById("unit-uk-btn");

  // Metadata Inputs
  const titleInput = document.getElementById("recipe-title");
  const servingsInput = document.getElementById("recipe-servings");
  const prepTimeInput = document.getElementById("recipe-prep-time");
  const cookTimeInput = document.getElementById("recipe-cook-time");
  const totalTimeInput = document.getElementById("recipe-total-time");

  // Dynamic Lists
  const ingredientsList = document.getElementById("ingredients-list");
  const stepsList = document.getElementById("steps-list");
  const notesList = document.getElementById("notes-list");
  const imagesSection = document.getElementById("images-section");
  const imageGallery = document.getElementById("image-gallery");

  const addIngredientBtn = document.getElementById("add-ingredient-btn");
  const addStepBtn = document.getElementById("add-step-btn");
  const addNoteBtn = document.getElementById("add-note-btn");

  // Preview Elements
  const prevTitle = document.getElementById("prev-title");
  const prevServingsBox = document.getElementById("prev-servings-box");
  const prevServings = document.getElementById("prev-servings");
  const prevPrepBox = document.getElementById("prev-prep-box");
  const prevPrep = document.getElementById("prev-prep");
  const prevCookBox = document.getElementById("prev-cook-box");
  const prevCook = document.getElementById("prev-cook");
  const prevTotalBox = document.getElementById("prev-total-box");
  const prevTotal = document.getElementById("prev-total");
  const prevImageContainer = document.getElementById("prev-image-container");
  const prevImage = document.getElementById("prev-image");
  const prevIngredientsList = document.getElementById("prev-ingredients-list");
  const prevStepsList = document.getElementById("prev-steps-list");
  const prevNotesSection = document.getElementById("prev-notes-section");
  const prevNotesList = document.getElementById("prev-notes-list");
  const prevSourceUrl = document.getElementById("prev-source-url");

  // Utilities
  function showAlert(message, type = "error") {
    alertBox.textContent = message;
    alertBox.className = `alert alert-${type}`;
    alertBox.style.display = "block";
  }

  function hideAlert() {
    alertBox.style.display = "none";
    alertBox.textContent = "";
  }

  function cloneRecipe(rec) {
    return JSON.parse(JSON.stringify(rec));
  }

  function autoResizeTextarea(el) {
    el.style.height = "auto";
    el.style.height = Math.max(el.scrollHeight, 42) + "px";
  }

  function setView(view) {
    if (view === "preview") {
      updateRecipeFromEditor();
      renderPreview();
      editorContainer.classList.add("hidden");
      previewContainer.classList.add("active");
      viewPreviewBtn.classList.add("active");
      viewEditBtn.classList.remove("active");
    } else {
      renderEditor();
      editorContainer.classList.remove("hidden");
      previewContainer.classList.remove("active");
      viewEditBtn.classList.add("active");
      viewPreviewBtn.classList.remove("active");
    }
  }

  // Update State from Inputs
  function updateRecipeFromEditor() {
    if (!currentRecipe) return;
    currentRecipe.title = titleInput.value.trim();
    currentRecipe.servings = servingsInput.value.trim() || null;
    currentRecipe.prep_time_minutes = prepTimeInput.value ? parseInt(prepTimeInput.value, 10) : null;
    currentRecipe.cook_time_minutes = cookTimeInput.value ? parseInt(cookTimeInput.value, 10) : null;
    currentRecipe.total_time_minutes = totalTimeInput.value ? parseInt(totalTimeInput.value, 10) : null;
  }

  // Drag and Drop Helper
  function setupDragAndDrop(row, listType, getIndex, getArray, renderFn) {
    row.draggable = true;

    row.addEventListener("dragstart", (e) => {
      draggedItem = { listType, index: getIndex() };
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", `${listType}:${getIndex()}`);
    });

    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      draggedItem = null;
      document.querySelectorAll(".list-row").forEach((el) => {
        el.classList.remove("drag-over-top", "drag-over-bottom");
      });
    });

    row.addEventListener("dragover", (e) => {
      if (!draggedItem || draggedItem.listType !== listType) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";

      const rect = row.getBoundingClientRect();
      const midY = rect.top + rect.height / 2;
      if (e.clientY < midY) {
        row.classList.add("drag-over-top");
        row.classList.remove("drag-over-bottom");
      } else {
        row.classList.add("drag-over-bottom");
        row.classList.remove("drag-over-top");
      }
    });

    row.addEventListener("dragleave", () => {
      row.classList.remove("drag-over-top", "drag-over-bottom");
    });

    row.addEventListener("drop", (e) => {
      if (!draggedItem || draggedItem.listType !== listType) return;
      e.preventDefault();
      e.stopPropagation();

      const fromIndex = draggedItem.index;
      let toIndex = getIndex();

      const rect = row.getBoundingClientRect();
      const midY = rect.top + rect.height / 2;
      const dropAfter = e.clientY >= midY;

      row.classList.remove("drag-over-top", "drag-over-bottom");

      if (fromIndex === toIndex) return;

      updateRecipeFromEditor();
      const arr = getArray();
      const [movedItem] = arr.splice(fromIndex, 1);

      if (fromIndex < toIndex && !dropAfter) {
        toIndex--;
      } else if (fromIndex > toIndex && dropAfter) {
        toIndex++;
      }

      arr.splice(toIndex, 0, movedItem);
      renderFn();
    });
  }

  // Render Editor View
  function renderEditor() {
    if (!currentRecipe) return;

    titleInput.value = currentRecipe.title || "";
    servingsInput.value = currentRecipe.servings || "";
    prepTimeInput.value = currentRecipe.prep_time_minutes ?? "";
    cookTimeInput.value = currentRecipe.cook_time_minutes ?? "";
    totalTimeInput.value = currentRecipe.total_time_minutes ?? "";

    renderImages();
    renderIngredients();
    renderSteps();
    renderNotes();
    updateUndoButton();
  }

  function renderImages() {
    imageGallery.innerHTML = "";
    if (!currentRecipe.images || currentRecipe.images.length === 0) {
      imagesSection.style.display = "none";
      return;
    }

    imagesSection.style.display = "block";
    currentRecipe.images.forEach((img, idx) => {
      const card = document.createElement("div");
      card.className = `image-card ${img.selected ? "selected" : ""}`;

      const imgEl = document.createElement("img");
      imgEl.src = img.src;
      imgEl.alt = img.alt || `Photo ${idx + 1}`;

      const label = document.createElement("label");
      label.textContent = img.selected ? "✓ Print Image" : "Click to select";

      card.appendChild(imgEl);
      card.appendChild(label);

      card.addEventListener("click", () => {
        currentRecipe.images.forEach((otherImg, otherIdx) => {
          otherImg.selected = otherIdx === idx && !img.selected;
        });
        renderImages();
      });

      imageGallery.appendChild(card);
    });
  }

  function updateUnitToggleButtons() {
    const current = (currentRecipe && currentRecipe.unit_system) || "original";
    [unitOrigBtn, unitMetricBtn, unitUkBtn].forEach((btn) => {
      if (btn) {
        if (btn.getAttribute("data-unit") === current) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      }
    });
  }

  async function switchUnitSystem(targetSystem) {
    if (!currentRecipe) return;
    updateRecipeFromEditor();

    if (targetSystem === "original") {
      // Revert ingredients and text
      currentRecipe.unit_system = "original";
      currentRecipe.ingredients.forEach((ing) => {
        ing.unit_override = null;
        if (ing.original_raw) {
          ing.raw = ing.original_raw;
        }
        ing.converted = null;
      });
      // Restore steps and notes from originalRecipe if available
      if (originalRecipe && originalRecipe.steps) {
        currentRecipe.steps.forEach((st, i) => {
          if (originalRecipe.steps[i]) {
            st.text = originalRecipe.steps[i].text;
          }
        });
      }
      if (originalRecipe && originalRecipe.notes) {
        currentRecipe.notes.forEach((nt, i) => {
          if (originalRecipe.notes[i]) {
            currentRecipe.notes[i] = originalRecipe.notes[i];
          }
        });
      }
      updateUnitToggleButtons();
      renderEditor();
      renderPreview();
      return;
    }

    try {
      const resp = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipe: currentRecipe,
          unit_system: targetSystem,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Failed to convert units.");
      }

      currentRecipe = data.recipe;
      updateUnitToggleButtons();
      renderEditor();
      renderPreview();
    } catch (err) {
      showAlert(err.message || "Unit conversion failed.", "error");
    }
  }

  function renderIngredients() {
    ingredientsList.textContent = "";
    currentRecipe.ingredients.forEach((ing, index) => {
      const row = document.createElement("div");
      row.className = "list-row";

      // Drag handle
      const handle = document.createElement("span");
      handle.className = "row-handle";
      handle.textContent = "⋮⋮";
      handle.title = "Drag to reorder";

      // Group input
      const groupInput = document.createElement("input");
      groupInput.type = "text";
      groupInput.className = "group-input";
      groupInput.placeholder = "Group (optional)";
      groupInput.value = ing.group || "";
      groupInput.addEventListener("input", (e) => {
        ing.group = e.target.value.trim() || null;
      });

      // Content column for textarea and conversion override helper
      const contentCol = document.createElement("div");
      contentCol.className = "ingredient-content-col";

      const displayText =
        currentRecipe.unit_system !== "original" && ing.converted && ing.unit_override !== "original"
          ? ing.converted
          : ing.raw;

      const rawTextarea = document.createElement("textarea");
      rawTextarea.placeholder = "Ingredient description";
      rawTextarea.value = displayText;
      rawTextarea.rows = 1;
      rawTextarea.addEventListener("input", (e) => {
        if (currentRecipe.unit_system !== "original" && ing.converted && ing.unit_override !== "original") {
          ing.converted = e.target.value;
        } else {
          ing.raw = e.target.value;
          ing.original_raw = e.target.value;
        }
        autoResizeTextarea(rawTextarea);
      });

      contentCol.appendChild(rawTextarea);

      // If converted and differs from original, show override / revert option
      const hasConversion =
        currentRecipe.unit_system !== "original" &&
        ing.converted &&
        ing.original_raw &&
        ing.converted !== ing.original_raw;

      if (hasConversion) {
        const hint = document.createElement("div");
        hint.className = "ingredient-override-hint";

        const origSpan = document.createElement("span");
        origSpan.textContent = `Orig: ${ing.original_raw}`;

        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.className = "btn-link";

        if (ing.unit_override === "original") {
          toggleBtn.textContent = "Use converted";
          toggleBtn.addEventListener("click", () => {
            ing.unit_override = null;
            renderIngredients();
          });
        } else {
          toggleBtn.textContent = "Revert to original";
          toggleBtn.addEventListener("click", () => {
            ing.unit_override = "original";
            renderIngredients();
          });
        }

        hint.appendChild(origSpan);
        hint.appendChild(toggleBtn);
        contentCol.appendChild(hint);
      }

      // Delete button
      const delBtn = document.createElement("button");
      delBtn.className = "btn-danger btn-icon btn-small";
      delBtn.textContent = "✕";
      delBtn.type = "button";
      delBtn.title = "Delete Ingredient";
      delBtn.addEventListener("click", () => {
        updateRecipeFromEditor();
        const [deleted] = currentRecipe.ingredients.splice(index, 1);
        deleteHistory.push({ type: "ingredient", index, item: deleted });
        renderIngredients();
        updateUndoButton();
      });

      row.appendChild(handle);
      row.appendChild(groupInput);
      row.appendChild(contentCol);
      row.appendChild(delBtn);

      setupDragAndDrop(
        row,
        "ingredient",
        () => index,
        () => currentRecipe.ingredients,
        renderIngredients
      );

      ingredientsList.appendChild(row);
      autoResizeTextarea(rawTextarea);
    });
  }

  function renderSteps() {
    stepsList.innerHTML = "";
    currentRecipe.steps.forEach((step, index) => {
      const row = document.createElement("div");
      row.className = "list-row";

      // Drag handle
      const handle = document.createElement("span");
      handle.className = "row-handle";
      handle.textContent = "⋮⋮";
      handle.title = "Drag to reorder";

      const stepTextarea = document.createElement("textarea");
      stepTextarea.placeholder = `Step ${index + 1} instruction`;
      stepTextarea.value = step.text;
      stepTextarea.rows = 2;
      stepTextarea.addEventListener("input", (e) => {
        step.text = e.target.value;
        autoResizeTextarea(stepTextarea);
      });

      const delBtn = document.createElement("button");
      delBtn.className = "btn-danger btn-icon btn-small";
      delBtn.textContent = "✕";
      delBtn.type = "button";
      delBtn.title = "Delete Step";
      delBtn.addEventListener("click", () => {
        updateRecipeFromEditor();
        const [deleted] = currentRecipe.steps.splice(index, 1);
        deleteHistory.push({ type: "step", index, item: deleted });
        renderSteps();
        updateUndoButton();
      });

      row.appendChild(handle);
      row.appendChild(stepTextarea);
      row.appendChild(delBtn);

      setupDragAndDrop(
        row,
        "step",
        () => index,
        () => currentRecipe.steps,
        renderSteps
      );

      stepsList.appendChild(row);
      autoResizeTextarea(stepTextarea);
    });
  }

  function renderNotes() {
    notesList.innerHTML = "";
    currentRecipe.notes.forEach((note, index) => {
      const row = document.createElement("div");
      row.className = "list-row";

      // Drag handle
      const handle = document.createElement("span");
      handle.className = "row-handle";
      handle.textContent = "⋮⋮";
      handle.title = "Drag to reorder";

      const noteTextarea = document.createElement("textarea");
      noteTextarea.placeholder = "Note / tip";
      noteTextarea.value = note;
      noteTextarea.rows = 2;
      noteTextarea.addEventListener("input", (e) => {
        currentRecipe.notes[index] = e.target.value;
        autoResizeTextarea(noteTextarea);
      });

      const delBtn = document.createElement("button");
      delBtn.className = "btn-danger btn-icon btn-small";
      delBtn.textContent = "✕";
      delBtn.type = "button";
      delBtn.title = "Delete Note";
      delBtn.addEventListener("click", () => {
        updateRecipeFromEditor();
        const [deleted] = currentRecipe.notes.splice(index, 1);
        deleteHistory.push({ type: "note", index, item: deleted });
        renderNotes();
        updateUndoButton();
      });

      row.appendChild(handle);
      row.appendChild(noteTextarea);
      row.appendChild(delBtn);

      setupDragAndDrop(
        row,
        "note",
        () => index,
        () => currentRecipe.notes,
        renderNotes
      );

      notesList.appendChild(row);
      autoResizeTextarea(noteTextarea);
    });
  }

  function updateUndoButton() {
    undoBtn.style.display = deleteHistory.length > 0 ? "inline-flex" : "none";
  }

  // Render Print Preview View
  function renderPreview() {
    if (!currentRecipe) return;

    prevTitle.textContent = currentRecipe.title || "Untitled Recipe";

    // Meta items
    if (currentRecipe.servings) {
      prevServings.textContent = currentRecipe.servings;
      prevServingsBox.style.display = "inline";
    } else {
      prevServingsBox.style.display = "none";
    }

    if (currentRecipe.prep_time_minutes) {
      prevPrep.textContent = currentRecipe.prep_time_minutes;
      prevPrepBox.style.display = "inline";
    } else {
      prevPrepBox.style.display = "none";
    }

    if (currentRecipe.cook_time_minutes) {
      prevCook.textContent = currentRecipe.cook_time_minutes;
      prevCookBox.style.display = "inline";
    } else {
      prevCookBox.style.display = "none";
    }

    if (currentRecipe.total_time_minutes) {
      prevTotal.textContent = currentRecipe.total_time_minutes;
      prevTotalBox.style.display = "inline";
    } else {
      prevTotalBox.style.display = "none";
    }

    // Selected Image
    const selectedImg = (currentRecipe.images || []).find((img) => img.selected);
    if (selectedImg) {
      prevImage.src = selectedImg.src;
      prevImage.alt = selectedImg.alt || currentRecipe.title;
      prevImageContainer.style.display = "block";
    } else {
      prevImageContainer.style.display = "none";
    }

    // Ingredients
    prevIngredientsList.textContent = "";
    let currentGroup = null;
    (currentRecipe.ingredients || []).forEach((ing) => {
      if (ing.group && ing.group !== currentGroup) {
        currentGroup = ing.group;
        const groupEl = document.createElement("li");
        groupEl.className = "ingredient-group-title";
        groupEl.textContent = currentGroup;
        prevIngredientsList.appendChild(groupEl);
      } else if (!ing.group && currentGroup !== null) {
        currentGroup = null;
      }

      const activeText =
        currentRecipe.unit_system !== "original" && ing.converted && ing.unit_override !== "original"
          ? ing.converted
          : ing.raw;

      if (activeText.trim()) {
        const itemEl = document.createElement("li");
        itemEl.textContent = activeText;
        prevIngredientsList.appendChild(itemEl);
      }
    });

    // Steps
    prevStepsList.innerHTML = "";
    (currentRecipe.steps || []).forEach((step) => {
      if (step.text.trim()) {
        const stepEl = document.createElement("li");
        stepEl.textContent = step.text;
        prevStepsList.appendChild(stepEl);
      }
    });

    // Notes
    prevNotesList.innerHTML = "";
    const validNotes = (currentRecipe.notes || []).filter((n) => n.trim());
    if (validNotes.length > 0) {
      prevNotesSection.style.display = "block";
      validNotes.forEach((n) => {
        const p = document.createElement("p");
        p.textContent = n;
        p.style.marginBottom = "0.5rem";
        prevNotesList.appendChild(p);
      });
    } else {
      prevNotesSection.style.display = "none";
    }

    // Source URL attribution
    if (currentRecipe.source_url) {
      prevSourceUrl.textContent = `Source: ${currentRecipe.source_url}`;
    } else {
      prevSourceUrl.textContent = "";
    }
  }

  // Event Listeners
  extractForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = recipeUrlInput.value.trim();
    if (!url) return;

    hideAlert();
    extractBtn.disabled = true;
    btnSpinner.style.display = "inline-block";
    btnText.textContent = "Extracting...";

    try {
      const response = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to extract recipe.");
      }

      originalRecipe = cloneRecipe(data.recipe);
      currentRecipe = cloneRecipe(data.recipe);
      deleteHistory.length = 0;

      workspace.style.display = "block";
      updateUnitToggleButtons();
      setView("edit");

      if (data.warnings && data.warnings.length > 0) {
        showAlert(`Note: ${data.warnings.join("; ")}`, "warning");
      }
    } catch (err) {
      showAlert(err.message || "An unexpected error occurred.", "error");
    } finally {
      extractBtn.disabled = false;
      btnSpinner.style.display = "none";
      btnText.textContent = "Extract Recipe";
    }
  });

  viewEditBtn.addEventListener("click", () => setView("edit"));
  viewPreviewBtn.addEventListener("click", () => setView("preview"));

  [unitOrigBtn, unitMetricBtn, unitUkBtn].forEach((btn) => {
    if (btn) {
      btn.addEventListener("click", () => {
        const unit = btn.getAttribute("data-unit");
        switchUnitSystem(unit);
      });
    }
  });

  addIngredientBtn.addEventListener("click", () => {
    updateRecipeFromEditor();
    currentRecipe.ingredients.push({ raw: "", group: null });
    renderIngredients();
    const rows = ingredientsList.querySelectorAll(".list-row");
    if (rows.length > 0) {
      const lastTextarea = rows[rows.length - 1].querySelector("textarea");
      if (lastTextarea) lastTextarea.focus();
    }
  });

  addStepBtn.addEventListener("click", () => {
    updateRecipeFromEditor();
    currentRecipe.steps.push({ text: "" });
    renderSteps();
    const rows = stepsList.querySelectorAll(".list-row");
    if (rows.length > 0) {
      const lastTextarea = rows[rows.length - 1].querySelector("textarea");
      if (lastTextarea) lastTextarea.focus();
    }
  });

  addNoteBtn.addEventListener("click", () => {
    updateRecipeFromEditor();
    currentRecipe.notes.push("");
    renderNotes();
    const rows = notesList.querySelectorAll(".list-row");
    if (rows.length > 0) {
      const lastTextarea = rows[rows.length - 1].querySelector("textarea");
      if (lastTextarea) lastTextarea.focus();
    }
  });

  undoBtn.addEventListener("click", () => {
    if (deleteHistory.length === 0) return;
    updateRecipeFromEditor();
    const lastDeleted = deleteHistory.pop();
    if (lastDeleted.type === "ingredient") {
      currentRecipe.ingredients.splice(lastDeleted.index, 0, lastDeleted.item);
      renderIngredients();
    } else if (lastDeleted.type === "step") {
      currentRecipe.steps.splice(lastDeleted.index, 0, lastDeleted.item);
      renderSteps();
    } else if (lastDeleted.type === "note") {
      currentRecipe.notes.splice(lastDeleted.index, 0, lastDeleted.item);
      renderNotes();
    }
    updateUndoButton();
  });

  resetBtn.addEventListener("click", () => {
    if (!originalRecipe) return;
    if (confirm("Reset recipe to original extracted version? Any edits will be lost.")) {
      currentRecipe = cloneRecipe(originalRecipe);
      deleteHistory.length = 0;
      renderEditor();
    }
  });

  printBtn.addEventListener("click", () => {
    updateRecipeFromEditor();
    renderPreview();
    window.print();
  });
})();
