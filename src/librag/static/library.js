// Copyright (C) 2026 Theo van Oostrum
// The Library page: add books with the file picker or by dropping files on the
// page, upload each one with POST /api/books, and show a notice for each refusal.
"use strict";

(() => {
  const picker = document.getElementById("book-picker");
  const overlay = document.querySelector(".drop-overlay");
  const maxUploadMb = document.body.dataset.maxUploadMb;

  function notices() {
    return document.getElementById("notices");
  }

  // Show "<em>name</em> rest" as a dismissable notice, above the books.
  function showNotice(name, rest) {
    const item = document.createElement("li");
    item.className = "notice";
    const text = document.createElement("span");
    text.className = "notice__text";
    const em = document.createElement("em");
    em.textContent = name;
    text.append(em, rest);
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "notice__dismiss";
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "Dismiss";
    item.append(text, dismiss);
    notices().append(item);
  }

  async function titleOf(bookId) {
    try {
      const response = await fetch("/api/books");
      const { books } = await response.json();
      const book = books.find((each) => each.id === bookId);
      return book ? book.title : null;
    } catch {
      return null;
    }
  }

  async function refuse(file, response) {
    if (response.status === 409) {
      const { book_id: bookId } = await response.json();
      showNotice((await titleOf(bookId)) || file.name, " is already in your library.");
    } else if (response.status === 422) {
      showNotice(file.name, " isn't an EPUB we can read.");
    } else if (response.status === 413) {
      showNotice(file.name, ` is larger than ${maxUploadMb} MB.`);
    } else {
      showNotice(file.name, " could not be added. Try again.");
    }
  }

  function refresh() {
    return htmx.ajax("GET", "/library/books", { target: "#library", swap: "outerHTML" });
  }

  // Upload the files one after the other, and show each new book as it lands.
  async function upload(files) {
    for (const file of files) {
      const body = new FormData();
      body.append("file", file);
      let response;
      try {
        response = await fetch("/api/books", { method: "POST", body });
      } catch {
        showNotice(file.name, " could not be added. Try again.");
        continue;
      }
      if (response.ok) {
        await refresh();
      } else {
        await refuse(file, response);
      }
    }
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-add-book]")) {
      picker.click();
      return;
    }
    const dismiss = event.target.closest(".notice__dismiss");
    if (dismiss) {
      dismiss.closest(".notice").remove();
    }
  });

  picker.addEventListener("change", () => {
    const files = Array.from(picker.files);
    picker.value = "";
    upload(files);
  });

  // Files dragged over the page show the overlay; dropping them uploads each one.
  // Enter and leave fire for every child element, so count them.
  let depth = 0;

  function hasFiles(event) {
    return Array.from(event.dataTransfer?.types || []).includes("Files");
  }

  function hideOverlay() {
    depth = 0;
    overlay.hidden = true;
  }

  document.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    depth += 1;
    overlay.hidden = false;
  });

  document.addEventListener("dragover", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });

  document.addEventListener("dragleave", (event) => {
    if (!hasFiles(event)) return;
    depth -= 1;
    if (depth <= 0) hideOverlay();
  });

  document.addEventListener("drop", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    hideOverlay();
    upload(Array.from(event.dataTransfer.files));
  });
})();
