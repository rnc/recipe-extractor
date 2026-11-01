// SPDX-License-Identifier: Apache-2.0

(function () {
  "use strict";

  // Application State
  let currentRecipe = null;
  let originalRecipe = null;
  const deleteHistory = [];

  // Drag and drop tracking
  let draggedItem = null;

  // Recipe library (auto-save). See PLAN.md section 10.2.
  const SAVE_DELAY_MS = 1000;
  let libraryEnabled = false;
  let libraryId = null;
  let libraryState = null;
  let libraryEditedAt = null;
  let hasPrevious = false;
  let editVersion = 0; // bumped on every edit
  let savedVersion = 0; // last editVersion known to be stored
  let saveTimer = null;
  let saveInFlight = null;
  let saveFailed = false;
  let nextState = "editing";
  let nextKeepPrevious = false;
  let openedFromLibrary = false;

  const STATE_LABELS = { extracted: "Extracted", editing: "Edited", final: "Printed" };

  // DOM Elements
  const extractForm = document.getElementById("extract-form");
  const recipeUrlInput = document.getElementById("recipe-url");
  const clearUrlBtn = document.getElementById("clear-url-btn");
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

  // Library elements
  const libraryCard = document.getElementById("library-card");
  const libraryPanel = document.getElementById("library-panel");
  const libraryCount = document.getElementById("library-count");
  const libraryEmpty = document.getElementById("library-empty");
  const libraryListEl = document.getElementById("library-list");
  const statusLine = document.getElementById("status-line");
  const libraryBadge = document.getElementById("library-badge");
  const saveStatus = document.getElementById("save-status");
  const saveRetryBtn = document.getElementById("save-retry-btn");
  const restoreBtn = document.getElementById("restore-btn");
  const reextractBtn = document.getElementById("reextract-btn");

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
      markDirty();
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
      markDirty();
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

  // ---- Recipe library and auto-save (PLAN.md section 10.2) ---------------
  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ""
      : d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
  }

  function hostOf(url) {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }

  function setSaveStatus(text, failed = false) {
    saveStatus.textContent = text;
    saveStatus.classList.toggle("save-failed", failed);
    saveRetryBtn.style.display = failed ? "inline-flex" : "none";
  }

  function updateLibraryControls() {
    const active = libraryEnabled && libraryId !== null;
    statusLine.style.display = active ? "flex" : "none";
    restoreBtn.style.display = active && hasPrevious ? "inline-flex" : "none";
    reextractBtn.style.display = active ? "inline-flex" : "none";
    // A recipe re-opened from the library has no session "original" to reset to.
    // Re-extract is the way back to a fresh copy.
    resetBtn.style.display = openedFromLibrary ? "none" : "inline-flex";
    if (active && libraryState) {
      libraryBadge.textContent = STATE_LABELS[libraryState] || libraryState;
      libraryBadge.dataset.state = libraryState;
      libraryBadge.title = libraryEditedAt
        ? `Last edited ${formatDate(libraryEditedAt)}`
        : "Not edited yet";
    } else {
      libraryBadge.textContent = "";
      delete libraryBadge.dataset.state;
    }
  }

  function markDirty() {
    if (!libraryEnabled || libraryId === null) return;
    editVersion += 1;
    nextState = "editing";
    setSaveStatus("Unsaved changes…");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flushSave, SAVE_DELAY_MS);
  }

  async function saveOnce() {
    updateRecipeFromEditor();
    const id = libraryId;
    const sentVersion = editVersion;
    const keepPrevious = nextKeepPrevious;
    setSaveStatus("Saving…");
    try {
      const resp = await fetch(`/api/library/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipe: currentRecipe,
          state: nextState,
          keep_previous: keepPrevious,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const record = await resp.json();
      if (libraryId !== id) return true; // another recipe was opened meanwhile
      savedVersion = sentVersion;
      if (keepPrevious) nextKeepPrevious = false;
      libraryState = record.state;
      libraryEditedAt = record.edited_at;
      hasPrevious = record.has_previous;
      saveFailed = false;
      setSaveStatus(editVersion === sentVersion ? "Saved" : "Unsaved changes…");
      updateLibraryControls();
      return true;
    } catch {
      saveFailed = true;
      setSaveStatus("Not saved – retry", true);
      return false;
    }
  }

  // Saves until everything edited so far is stored. Resolves false if a save fails.
  async function flushSave() {
    clearTimeout(saveTimer);
    saveTimer = null;
    while (libraryEnabled && libraryId !== null) {
      if (saveInFlight) {
        await saveInFlight;
        continue;
      }
      if (savedVersion >= editVersion && !saveFailed) return true;
      const ok = await (saveInFlight = saveOnce().finally(() => {
        saveInFlight = null;
      }));
      if (!ok) return false;
    }
    return true;
  }

  // True when it is safe to replace the current recipe on screen.
  async function ensureSaved() {
    if (await flushSave()) return true;
    return confirm("Your latest changes could not be saved. Continue and lose them?");
  }

  function applyLoaded(info) {
    originalRecipe = cloneRecipe(info.recipe);
    currentRecipe = cloneRecipe(info.recipe);
    deleteHistory.length = 0;

    libraryId = info.libraryId ?? null;
    libraryState = info.state ?? null;
    libraryEditedAt = info.editedAt ?? null;
    hasPrevious = Boolean(info.hasPrevious);
    openedFromLibrary = Boolean(info.fromLibrary);
    editVersion = 0;
    savedVersion = 0;
    saveFailed = false;
    nextState = "editing";
    nextKeepPrevious = false;
    clearTimeout(saveTimer);

    workspace.style.display = "block";
    updateUnitToggleButtons();
    setView("edit");
    setSaveStatus(libraryId !== null ? "Saved" : "");
    updateLibraryControls();
  }

  function renderLibrary(entries) {
    libraryListEl.textContent = "";
    libraryCount.textContent = entries.length ? `(${entries.length})` : "";
    libraryEmpty.style.display = entries.length ? "none" : "block";

    entries.forEach((entry) => {
      const item = document.createElement("li");
      item.className = "library-item";

      const info = document.createElement("div");
      info.className = "library-info";
      const title = document.createElement("strong");
      title.textContent = entry.title || "Untitled Recipe";
      const meta = document.createElement("span");
      meta.className = "library-meta";
      const when = formatDate(entry.edited_at || entry.extracted_at);
      meta.textContent = [STATE_LABELS[entry.state] || entry.state, when, hostOf(entry.url)]
        .filter(Boolean)
        .join(" · ");
      info.appendChild(title);
      info.appendChild(meta);

      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "btn-secondary btn-small";
      openBtn.textContent = "Open";
      openBtn.addEventListener("click", () => openFromLibrary(entry.id));

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn-danger btn-small";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => deleteFromLibrary(entry));

      item.appendChild(info);
      item.appendChild(openBtn);
      item.appendChild(delBtn);
      libraryListEl.appendChild(item);
    });
  }

  async function refreshLibrary() {
    if (!libraryEnabled) return;
    try {
      const resp = await fetch("/api/library");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      renderLibrary(await resp.json());
    } catch {
      showAlert("Could not load the saved recipes.", "error");
    }
  }

  function loadedFromRecord(record, fromLibrary) {
    return {
      recipe: record.recipe,
      libraryId: record.id,
      state: record.state,
      editedAt: record.edited_at,
      hasPrevious: record.has_previous,
      fromLibrary,
    };
  }

  async function openFromLibrary(id) {
    if (!(await ensureSaved())) return;
    hideAlert();
    try {
      const resp = await fetch(`/api/library/${id}`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Could not open the recipe.");
      applyLoaded(loadedFromRecord(data, true));
      libraryPanel.open = false;
      window.scrollTo({ top: 0 });
    } catch (err) {
      showAlert(err.message || "Could not open the recipe.", "error");
    }
  }

  async function deleteFromLibrary(entry) {
    const name = entry.title || "Untitled Recipe";
    if (!confirm(`Delete "${name}" from your saved recipes? This cannot be undone.`)) {
      return;
    }
    try {
      const resp = await fetch(`/api/library/${entry.id}`, { method: "DELETE" });
      if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);
      if (entry.id === libraryId) {
        clearTimeout(saveTimer);
        libraryId = null;
        currentRecipe = null;
        originalRecipe = null;
        workspace.style.display = "none";
      }
      await refreshLibrary();
    } catch {
      showAlert("Could not delete the recipe.", "error");
    }
  }

  async function initLibrary() {
    try {
      const resp = await fetch("/api/health");
      libraryEnabled = Boolean((await resp.json()).library);
    } catch {
      libraryEnabled = false;
    }
    libraryCard.style.display = libraryEnabled ? "block" : "none";
    refreshLibrary();
  }

  // Every edit marks the recipe dirty. Delegated so rows added later are covered.
  editorContainer.addEventListener("input", markDirty);
  editorContainer.addEventListener("click", (e) => {
    if (e.target.closest("button, .image-card")) markDirty();
  });
  // Row drop handlers stop propagation, so listen in the capture phase.
  editorContainer.addEventListener("drop", markDirty, true);

  libraryPanel.addEventListener("toggle", () => {
    if (libraryPanel.open) refreshLibrary();
  });
  saveRetryBtn.addEventListener("click", flushSave);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushSave();
  });
  window.addEventListener("beforeunload", (e) => {
    if (libraryId !== null && (savedVersion < editVersion || saveFailed)) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  restoreBtn.addEventListener("click", async () => {
    if (libraryId === null || !(await ensureSaved())) return;
    try {
      const resp = await fetch(`/api/library/${libraryId}/restore`, { method: "POST" });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Could not restore the previous version.");
      applyLoaded(loadedFromRecord(data, true));
      showAlert("Restored the previous version. Click Restore again to swap back.", "warning");
      refreshLibrary();
    } catch (err) {
      showAlert(err.message || "Could not restore the previous version.", "error");
    }
  });

  reextractBtn.addEventListener("click", async () => {
    if (libraryId === null || !(await ensureSaved())) return;
    hideAlert();
    const url = `/api/library/${libraryId}/re-extract`;
    reextractBtn.disabled = true;
    try {
      const preview = await fetch(url, { method: "POST" });
      const previewData = await preview.json();
      if (!preview.ok) throw new Error(previewData.detail || "Could not re-extract the recipe.");
      if (previewData.changes.length === 0) {
        showAlert("Your saved copy already matches the source page.", "warning");
        return;
      }
      const summary = previewData.changes.map((c) => `• ${c}`).join("\n");
      const proceed = confirm(
        `The source page differs from your saved copy:\n\n${summary}\n\n` +
          "Replace your saved copy with a fresh extraction? Your current version is kept, " +
          "and 'Restore previous version' brings it back."
      );
      if (!proceed) return;

      const applied = await fetch(`${url}?confirm=true`, { method: "POST" });
      const appliedData = await applied.json();
      if (!applied.ok) throw new Error(appliedData.detail || "Could not re-extract the recipe.");
      applyLoaded(loadedFromRecord(appliedData.record, false));
      refreshLibrary();
    } catch (err) {
      showAlert(err.message || "Could not re-extract the recipe.", "error");
    } finally {
      reextractBtn.disabled = false;
    }
  });

  // Event Listeners
  function updateClearUrlButton() {
    clearUrlBtn.style.display = recipeUrlInput.value ? "inline-flex" : "none";
  }

  recipeUrlInput.addEventListener("input", updateClearUrlButton);
  clearUrlBtn.addEventListener("click", () => {
    recipeUrlInput.value = "";
    updateClearUrlButton();
    recipeUrlInput.focus();
  });

  extractForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = recipeUrlInput.value.trim();
    if (!url) return;
    if (!(await ensureSaved())) return;

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

      applyLoaded({
        recipe: data.recipe,
        libraryId: data.library_id,
        state: data.state,
        editedAt: data.edited_at,
        hasPrevious: data.has_previous,
        fromLibrary: data.from_library,
      });
      if (data.library_id !== null) refreshLibrary();

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
  viewPreviewBtn.addEventListener("click", () => {
    setView("preview");
    flushSave();
  });

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
    markDirty();
  });

  resetBtn.addEventListener("click", async () => {
    if (!originalRecipe) return;
    const saved = libraryId !== null;
    const message = saved
      ? "Reset recipe to the version extracted in this session? Your edits are kept, and " +
        "'Restore previous version' brings them back."
      : "Reset recipe to original extracted version? Any edits will be lost.";
    if (!confirm(message)) return;
    if (saved && !(await ensureSaved())) return;

    currentRecipe = cloneRecipe(originalRecipe);
    deleteHistory.length = 0;
    renderEditor();
    if (saved) {
      nextKeepPrevious = true;
      markDirty();
      await flushSave();
    }
  });

  printBtn.addEventListener("click", () => {
    updateRecipeFromEditor();
    renderPreview();
    if (libraryId !== null) {
      editVersion += 1;
      nextState = "final";
      flushSave(); // starts the save before the print dialog blocks the page
    }
    window.print();
  });

  initLibrary();
})();
