// Copyright (C) 2026 Theo van Oostrum
// Drive the Chat page in headless Chromium, as a user does, and save
// screenshots and a transcript. Needs Node and Playwright (the cloud container
// has both; on a Mac, `npm i -g playwright` and `npx playwright install chromium`).
//
// Usage: node chat-browser.js <url> <evidence dir> <action> <platform>
//   no-books  screenshot the page of a library with no indexed book
//   chat      the whole flow: start, book picker, streaming, answer, follow-up,
//             new conversation, a failed answer and "Try again", model memory
//   diagnostics  "How this answer was found": the open panel, "Show all", a
//             rewritten follow-up, rerank off, and a failed turn without it
// <platform> is desktop (1280x800) or mobile (390x844).
//
// The fake LLM answers at once, so the page's fetch is wrapped: it passes the
// server's events through one at a time, and can hold them after the first
// part (for the streaming screenshot). For the failed answer it replaces the
// server's stream with a provider error, which only a live or scripted LLM gives.
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const WINDOWS = { desktop: { width: 1280, height: 800 }, mobile: { width: 390, height: 844 } };
const PROVIDER_ERROR = "Rate limit reached for gpt-6.1-terra. Try again in a minute.";

function wrapFetch() {
  window.__chat = { hold: false, release: null, fail: null, noRerank: false };
  const realFetch = window.fetch.bind(window);
  const encoder = new TextEncoder();
  window.fetch = async (input, init) => {
    if (!String(input).endsWith("/api/chat/stream")) return realFetch(input, init);
    const control = window.__chat;
    if (control.fail) {
      const events = [
        'event: status\ndata: {"step": "searching"}\n\n',
        `event: error\ndata: ${JSON.stringify({ message: control.fail })}\n\n`,
      ];
      return new Response(new Blob(events), { headers: { "content-type": "text/event-stream" } });
    }
    const response = await realFetch(input, init);
    if (!response.ok) return response;
    const text = await response.text();
    let blocks = text.split("\n\n").filter((b) => b.trim());
    if (control.noRerank) {
      // The stack always reranks; this is the `done` event of a search without it.
      blocks = blocks.map((block) => {
        if (!block.startsWith("event: done")) return block;
        const done = JSON.parse(block.slice(block.indexOf("data: ") + 6));
        done.retrieval.stages.rerank = { passages: [], time_ms: 0 };
        done.retrieval.settings.rerank = false;
        return `event: done\ndata: ${JSON.stringify(done)}`;
      });
    }
    const body = new ReadableStream({
      async start(controller) {
        for (const block of blocks) {
          controller.enqueue(encoder.encode(`${block}\n\n`));
          await new Promise((resolve) => setTimeout(resolve, 50));
          if (block.startsWith("event: part") && control.hold) {
            await new Promise((resolve) => { control.release = resolve; });
          }
        }
        controller.close();
      },
    });
    return new Response(body, { status: response.status, headers: response.headers });
  };
}

async function summary(page) {
  return page.evaluate(() => {
    const form = document.querySelector("form.ask");
    return {
      intro: document.querySelector(".chat-intro:not([hidden]) .chat-intro__title")?.textContent.trim() ?? null,
      head: Boolean(document.querySelector(".chat-head:not([hidden])")),
      turns: [...document.querySelectorAll(".turn")].map((turn) => ({
        question: turn.querySelector(".question").textContent.trim(),
        status: [...turn.querySelectorAll(".stream-status li")].map((li) => li.textContent.trim()),
        parts: [...turn.querySelectorAll(".answer > p")].map((p) => p.textContent.trim()),
        sources: [...turn.querySelectorAll(".source summary")].map((s) => s.textContent.trim()),
        diagnostics: turn.querySelectorAll(".diagnostics").length,
        error: turn.querySelector(".turn-error .notice__text")?.textContent.trim() ?? null,
      })),
      askDisabled: form.querySelector(".ask__input").disabled,
      askButtonDisabled: form.querySelector(".ask__bar button").disabled,
      model: form.querySelector("select").value,
      books: form.querySelector(".picker__toggle").textContent.trim(),
    };
  });
}

async function panel(page, turnIndex) {
  return page.evaluate((index) => {
    const turn = document.querySelectorAll(".turn")[index];
    const details = turn.querySelector(".diagnostics");
    if (!details) return { diagnostics: false };
    return {
      diagnostics: true,
      open: details.open,
      summary: [...details.querySelectorAll(".diag-summary > div")].map(
        (row) => `${row.querySelector("dt").textContent}: ${row.querySelector("dd").textContent}`,
      ),
      cards: [...details.querySelectorAll(".diag-card")].map((card) => ({
        head: card.querySelector(".diag-card__head").textContent,
        sent: card.classList.contains("diag-card--ctx"),
        words: card.querySelector(".diag-words").textContent,
        chips: [...card.querySelectorAll(".diag-chips span")].map((c) => c.textContent),
      })),
      more: details.querySelector(".diag > button")?.textContent ?? null,
    };
  }, turnIndex);
}

async function main() {
  const [url, out, action, platform] = process.argv.slice(2);
  if (!url || !out || !action || !WINDOWS[platform]) {
    throw new Error("usage: chat-browser.js <url> <evidence dir> <no-books|chat|diagnostics> <desktop|mobile>");
  }
  fs.mkdirSync(out, { recursive: true });
  const log = [];
  const note = (line) => { log.push(line); console.log(line); };
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: WINDOWS[platform] });
  await context.addInitScript(wrapFetch);
  const page = await context.newPage();
  const external = [];
  const sent = [];
  const requests = [];
  page.on("request", (request) => {
    requests.push(`${request.method()} ${request.url()}`);
    if (!request.url().startsWith(url)) external.push(request.url());
    if (request.url().endsWith("/api/chat/stream")) sent.push(JSON.parse(request.postData()));
  });
  const shot = async (name) => {
    // The gallery draws no focus, so the screenshot is taken without it.
    await page.evaluate(() => document.activeElement?.blur());
    await page.mouse.move(0, 0);
    await page.screenshot({ path: path.join(out, `app_${name}_${platform}.png`) });
    note(`screenshot: app_${name}_${platform}.png`);
  };
  const state = async (label) => note(`${label}: ${JSON.stringify(await summary(page))}`);
  const lastSent = () => JSON.stringify(sent[sent.length - 1]);
  const ask = async (question) => {
    await page.fill(".ask__input", question);
    await page.click(".ask__bar button");
  };
  const answered = (n) => page.waitForFunction(
    (count) => document.querySelectorAll(".turn .diagnostics, .turn .turn-error").length >= count, n,
  );

  await page.goto(`${url}/chat`);
  note(`open ${url}/chat (${platform})`);
  await state("loaded");

  if (action === "no-books") {
    await shot("no_books");
  } else if (action === "chat") {
    await shot("start");

    // The book picker: untick one author, then tick one book back.
    await page.click(".picker__toggle");
    const authors = await page.$$eval(".picker__group .picker__author", (ls) => ls.map((l) => l.textContent.trim()));
    note(`picker opened: authors ${JSON.stringify(authors)}`);
    const second = page.locator(".picker__group").nth(1);
    await second.locator(".picker__author input").uncheck();
    note(`unticked author ${authors[1]}: its books ticked = ${JSON.stringify(await second.locator(".picker__book input").evaluateAll((bs) => bs.map((b) => b.checked)))}`);
    await second.locator(".picker__author input").check();
    note(`ticked author ${authors[1]}: its books ticked = ${JSON.stringify(await second.locator(".picker__book input").evaluateAll((bs) => bs.map((b) => b.checked)))}`);
    await second.locator(".picker__book input").first().uncheck();
    await state("one book unticked");
    await shot("book_picker");
    await page.keyboard.press("Escape");

    // Ask, and hold the stream after its first part.
    await page.evaluate(() => { window.__chat.hold = true; });
    await ask("What did the lighthouse keeper do every evening?");
    await page.waitForFunction(() => window.__chat.release !== null);
    await state("streaming");
    note(`sent: ${lastSent()}`);
    await shot("streaming");
    await page.evaluate(() => { window.__chat.hold = false; window.__chat.release(); });
    await answered(1);
    await state("answered");
    await shot("answer");

    // A follow-up sends the first turn.
    await ask("And what did the keeper log?");
    await answered(2);
    note(`follow-up sent: ${lastSent()}`);
    await state("two turns");
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot("conversation");

    await page.click("[data-new-conversation]");
    await state("new conversation");

    // A failed answer, then "Try again".
    await page.evaluate((message) => { window.__chat.fail = message; }, PROVIDER_ERROR);
    await ask("Which of the books mentions the harbour?");
    await answered(1);
    await state("failed");
    await shot("error");
    await page.evaluate(() => { window.__chat.fail = null; });

    // Ask on after the failure; then "Try again" with no book ticked does nothing.
    await ask("And what did the keeper log?");
    await answered(2);
    await page.click(".picker__toggle");
    await page.locator("input[data-all]").check();
    await page.locator("input[data-all]").uncheck();
    note(`no book ticked: ask button disabled ${await page.locator(".ask__bar button").isDisabled()}, try again disabled ${await page.locator(".turn-error button").isDisabled()}`);
    await page.locator("input[data-all]").check();
    await page.keyboard.press("Escape");

    // "Try again" replaces the failed turn where it is, and sends only the turns before it.
    await page.click(".turn-error button");
    await page.waitForFunction(() => document.querySelectorAll(".turn .diagnostics").length === 2);
    note(`try again sent: ${lastSent()}`);
    await state("tried again");

    // The model is remembered after a reload.
    await page.selectOption("select[name=model]", { label: "GPT 6.1 Terra" });
    await page.reload();
    await state("reloaded after picking GPT 6.1 Terra");
    await ask("lighthouse");
    await answered(1);
    note(`sent after reload: ${lastSent()}`);
  } else if (action === "diagnostics") {
    const brief = (p) => ({ ...p, cards: `${p.cards?.length} cards`, first: p.cards?.slice(0, 3), last: p.cards?.at(-1) });
    await ask("What did the lighthouse keeper do every evening?");
    await answered(1);
    note(`answered, panel closed: ${JSON.stringify(await page.evaluate(() => document.querySelector(".diagnostics").open))}`);
    const before = requests.length;
    await page.click(".diagnostics > summary");
    note(`requests while opening the panel: ${JSON.stringify(requests.slice(before))}`);
    note(`opened: ${JSON.stringify(brief(await panel(page, 0)))}`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot("diagnostics");
    // The cards sit below the fold: a second pair of screenshots, app and
    // gallery, each scrolled so the panel starts at the top.
    const toPanel = () => document.querySelector(".diagnostics").scrollIntoView({ block: "start" });
    await page.evaluate(toPanel);
    await shot("diagnostics_cards");
    const gallery = await context.newPage();
    await gallery.goto(`file://${path.resolve("design/pages/chat/diagnostics.html")}`);
    await gallery.evaluate(toPanel);
    await gallery.screenshot({ path: path.join(out, `gallery_diagnostics_cards_${platform}.png`) });
    note(`screenshot: gallery_diagnostics_cards_${platform}.png`);
    await gallery.close();
    await page.locator(".diag-card .diag-words").first().click();
    note(`first words opened: ${JSON.stringify(await page.locator(".diag-card .diag-text").first().textContent())}`);
    if (await page.locator(".diag > button").count()) {
      await page.click(".diag > button");
      note(`after show all: ${JSON.stringify(brief(await panel(page, 0)))}`);
    }

    // A follow-up is rewritten into its own search query.
    await ask("And what did the keeper log?");
    await answered(2);
    await page.locator(".diagnostics > summary").nth(1).click();
    note(`follow-up summary: ${JSON.stringify((await panel(page, 1)).summary)}`);

    // Rerank off: no rerank tag, and the cards in fusion order.
    await page.evaluate(() => { window.__chat.noRerank = true; });
    await ask("lighthouse keeper brass lamp");
    await answered(3);
    await page.evaluate(() => { window.__chat.noRerank = false; });
    await page.locator(".diagnostics > summary").nth(2).click();
    const off = await panel(page, 2);
    const fusion = off.cards.map((card) => Number(card.chips[2].split(" ")[1]));
    note(`rerank off: ${JSON.stringify(brief(off))}`);
    note(`rerank off: rerank tags ${JSON.stringify([...new Set(off.cards.map((c) => c.chips[3]))])}, fusion order ${fusion.every((v, i) => i === 0 || v <= fusion[i - 1])}`);

    // A failed turn has no diagnostics.
    await page.evaluate((message) => { window.__chat.fail = message; }, PROVIDER_ERROR);
    await ask("Which of the books mentions the harbour?");
    await answered(4);
    note(`failed turn: ${JSON.stringify(await panel(page, 3))}`);
  } else {
    throw new Error(`unknown action ${action}`);
  }
  note(`external requests: ${JSON.stringify(external)}`);
  fs.writeFileSync(path.join(out, `browser_${action}_${platform}.txt`), `${log.join("\n")}\n`);
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
