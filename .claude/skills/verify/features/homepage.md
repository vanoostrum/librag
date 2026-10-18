# Homepage

A browser or client that opens `/` gets a small HTML page titled `LibRag` with the heading `LibRag`.

## Sub-features

- `homepage-html` returns 200 with an HTML content type.
- `homepage-content` has the title `LibRag` and the heading `LibRag`.

## How to get to it (user POV)

- Open `http://127.0.0.1:<port>/` in a browser, or send `GET /`.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.

- **Open the page.** Run `$V get homepage /`. Status is `200`.
- **Check the type.** Read `.verify/$LIBRAG_VERIFY_RUN/evidence/homepage/root.headers`. It has `content-type: text/html; charset=utf-8`.
- **Check the content.** Run `grep -c '<title>LibRag</title>\|<h1>LibRag</h1>' .verify/$LIBRAG_VERIFY_RUN/evidence/homepage/root.body`. The count is `2`.

## Gotchas

- The page has no CSS, scripts, or links. A test that expects assets fails for the right reason.
- The body starts with `<!DOCTYPE html>`. Compare markup, not a rendered screenshot.
