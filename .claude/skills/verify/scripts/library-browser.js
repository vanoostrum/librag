// Copyright (C) 2026 Theo van Oostrum
// Drive the Library page in headless Chromium, as a user does, and save
// screenshots and a transcript. Needs Node and Playwright (the cloud container
// has both; on a Mac, `npm i -g playwright` and `npx playwright install chromium`).
//
// Usage: node library-browser.js <url> <evidence dir> <action> <platform> [files... | title ...]
//   add      click "Add a book", choose <files> in the file picker, wait for the uploads
//   refused  as add, then screenshot the notices, then click the first "Dismiss"
//   drop     drag <files> over the page, screenshot the overlay, then drop them
//   confirm  click Delete on the card titled <title>, screenshot the confirmation,
//            click Cancel; with a third argument `delete`, then delete the book
//   act      click <Retry|Reindex> on the card titled <title>, then wait until
//            the refresh shows the book indexed
//   reindex-all  click "Reindex N out-of-date books", then wait until the refresh
//            shows no out-of-date book
// <platform> is desktop (1280x800) or mobile (390x844).
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const WINDOWS = { desktop: { width: 1280, height: 800 }, mobile: { width: 390, height: 844 } };

async function summary(page) {
  return page.evaluate(() => ({
    cards: [...document.querySelectorAll(".book-card")].map((card) => ({
      title: card.querySelector(".book-card__title").textContent.trim(),
      status: card.querySelector(".status").textContent.trim(),
      statusVisible: card.querySelector(".status").checkVisibility(),
      note: card.querySelector(".status-note")?.textContent.trim() || null,
      actions: [...card.querySelectorAll(".action-links a")].filter((a) => a.checkVisibility()).map((a) => a.textContent.trim()),
      confirm: card.querySelector(".confirm")?.checkVisibility()
        ? card.querySelector(".confirm").textContent.replace(/\s+/g, " ").trim()
        : null,
    })),
    headButtons: [...document.querySelectorAll(".page-head button")].map((b) => b.textContent.trim()),
    focused: document.activeElement === document.body ? null : document.activeElement?.textContent.trim() || null,
    notices: [...document.querySelectorAll(".notice__text")].map((n) => n.textContent.trim()),
    overlayVisible: getComputedStyle(document.querySelector(".drop-overlay")).display !== "none",
    polling: document.getElementById("library").getAttribute("hx-trigger"),
  }));
}

// Wait until the page has sent every upload and shown its result.
async function settle(page, uploads) {
  for (let seen = 0; seen < uploads; seen += 1) {
    await page.waitForResponse((r) => r.url().endsWith("/api/books") && r.request().method() === "POST");
  }
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
}

async function main() {
  const [url, out, action, platform, ...files] = process.argv.slice(2);
  if (!url || !out || !action || !WINDOWS[platform]) {
    throw new Error("usage: library-browser.js <url> <evidence dir> <add|refused|drop|confirm|act|reindex-all> <desktop|mobile> [files... | title ...]");
  }
  fs.mkdirSync(out, { recursive: true });
  const log = [];
  const note = (line) => { log.push(line); console.log(line); };
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: WINDOWS[platform] });
  const external = [];
  page.on("request", (request) => {
    if (!request.url().startsWith(url)) external.push(request.url());
  });
  await page.goto(`${url}/`);
  note(`open ${url}/ (${platform})`);
  note(`before: ${JSON.stringify(await summary(page))}`);

  if (action === "add" || action === "refused") {
    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.click("[data-add-book]"),
    ]);
    note(`file picker: multiple=${chooser.isMultiple()} accept=${await page.getAttribute("#book-picker", "accept")}`);
    await chooser.setFiles(files);
    note(`chose: ${files.map((f) => path.basename(f)).join(", ")}`);
    await settle(page, files.length);
    note(`after: ${JSON.stringify(await summary(page))}`);
    if (action === "refused") {
      // The grid refreshes every 2 seconds while a book is in progress; the notices stay.
      await page.waitForTimeout(2500);
      note(`after a refresh: ${JSON.stringify((await summary(page)).notices)}`);
      await page.mouse.move(0, 0);
      await page.screenshot({ path: path.join(out, `app_upload_error_${platform}.png`) });
      note(`screenshot: app_upload_error_${platform}.png`);
      await page.click(".notice__dismiss");
      note(`dismissed the first notice: ${JSON.stringify((await summary(page)).notices)}`);
    } else {
      await page.mouse.move(0, 0);
      await page.screenshot({ path: path.join(out, `app_added_${platform}.png`) });
      note(`screenshot: app_added_${platform}.png`);
    }
  } else if (action === "drop") {
    const payload = files.map((f) => ({ name: path.basename(f), bytes: [...fs.readFileSync(f)] }));
    const transfer = await page.evaluateHandle((items) => {
      const data = new DataTransfer();
      for (const item of items) {
        data.items.add(new File([new Uint8Array(item.bytes)], item.name, { type: "application/epub+zip" }));
      }
      return data;
    }, payload);
    await page.dispatchEvent("main", "dragenter", { dataTransfer: transfer });
    await page.dispatchEvent("main", "dragover", { dataTransfer: transfer });
    note(`dragging ${payload.map((p) => p.name).join(", ")}: ${JSON.stringify(await summary(page))}`);
    await page.screenshot({ path: path.join(out, `app_dropping_${platform}.png`) });
    note(`screenshot: app_dropping_${platform}.png`);
    await page.dispatchEvent(".drop-overlay", "drop", { dataTransfer: transfer });
    await settle(page, payload.length);
    note(`after drop: ${JSON.stringify(await summary(page))}`);
  } else if (action === "confirm") {
    const [title, then] = files;
    const card = page.locator(".book-card", { has: page.locator(".book-card__title", { hasText: title }) });
    await card.locator("[data-delete]").click();
    note(`clicked Delete on ${title}: ${JSON.stringify(await summary(page))}`);
    // The grid would refresh every 2 seconds; it waits while the question is open.
    await page.waitForTimeout(2500);
    note(`after 2.5 s: ${JSON.stringify((await summary(page)).cards.find((c) => c.title === title))}`);
    await page.mouse.move(0, 0);
    await page.screenshot({ path: path.join(out, `app_delete_confirm_${platform}.png`) });
    note(`screenshot: app_delete_confirm_${platform}.png`);
    await card.locator("[data-cancel]").click();
    note(`clicked Cancel: ${JSON.stringify((await summary(page)).cards.find((c) => c.title === title))}`);
    if (then === "delete") {
      await card.locator("[data-delete]").click();
      const [response] = await Promise.all([
        page.waitForResponse((r) => r.request().method() === "DELETE"),
        card.locator(".confirm .button-danger").click(),
      ]);
      note(`DELETE ${new URL(response.url()).pathname}: ${response.status()}`);
      await page.waitForResponse((r) => r.url().endsWith("/library/books"));
      await page.waitForTimeout(300);
      note(`after delete: ${JSON.stringify(await summary(page))}`);
    }
  } else if (action === "act" || action === "reindex-all") {
    const [title, link] = files;
    const control = action === "act"
      ? page.locator(".book-card", { has: page.locator(".book-card__title", { hasText: title }) }).locator(".action-links a", { hasText: link })
      : page.locator(".page-head__actions .button-quiet");
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === "POST" && r.url().includes("/api/books/")),
      control.click(),
    ]);
    note(`POST ${new URL(response.url()).pathname}: ${response.status()} ${await response.text()}`);
    await page.waitForResponse((r) => r.url().endsWith("/library/books"));
    await page.waitForTimeout(100);
    note(`right after: ${JSON.stringify(await summary(page))}`);
    // Done when the acted-on books are indexed and up to date again. Another
    // book in progress keeps the refresh going, so it cannot be the signal.
    const done = (state) => (action === "act"
      ? state.cards.find((c) => c.title === title).status.startsWith("Indexed")
      : state.cards.every((c) => !c.note && !/^(Waiting|Reading)/.test(c.status)));
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline && !done(await summary(page))) {
      await page.waitForTimeout(500);
    }
    note(`after the refresh: ${JSON.stringify(await summary(page))}`);
  } else {
    throw new Error(`unknown action ${action}`);
  }
  note(`external requests: ${JSON.stringify(external)}`);
  const suffix = action === "act" ? `_${files[1].toLowerCase()}` : "";
  fs.writeFileSync(path.join(out, `browser_${action}${suffix}_${platform}.txt`), `${log.join("\n")}\n`);
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
