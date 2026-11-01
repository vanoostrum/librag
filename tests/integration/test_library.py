# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for the Library page at GET / and its book grid at GET /library/books.

The pages are checked against the gallery pages in `design/pages/library/`.
"""

import re
from collections.abc import Callable
from http import HTTPStatus
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from lxml import html
from sqlalchemy import Engine, update

from librag.db import books
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

POLL = "every 2s"


_SIMPLE = re.compile(r'([#.]?[\w-]+|\*|\[[\w-]+(?:="[^"]*")?\])')


def _xpath_step(compound: str) -> str:
    """Return the XPath step for a compound CSS selector, such as `ul.notices`."""
    tag, tests = "*", list[str]()
    for part in map(str, _SIMPLE.findall(compound)):
        if part.startswith("."):
            tests.append(f"contains(concat(' ', @class, ' '), ' {part[1:]} ')")
        elif part.startswith("#"):
            tests.append(f"@id='{part[1:]}'")
        elif part.startswith("["):
            name, _, value = part[1:-1].partition("=")
            tests.append(f"@{name}={value}" if value else f"@{name}")
        else:
            tag = part
    return tag + "".join(f"[{test}]" for test in tests)


def select(root: html.HtmlElement, selector: str) -> list[html.HtmlElement]:
    """Return the elements under `root` that match a simple CSS `selector`.

    It knows tags, `#id`, `.class`, `[attr]`, `[attr="value"]`, `*`, the
    descendant and child combinators, and lists separated by commas.
    """
    paths = []
    for alternative in selector.split(","):
        path, axis = ".", "//"
        for step in alternative.split():
            if step == ">":
                axis = "/"
                continue
            path += axis + _xpath_step(step)
            axis = "//"
        paths.append(path)
    return root.xpath(" | ".join(paths))


def book(n: int, title: str | None = None, author: str | None = "Ada Writer") -> bytes:
    """Return a fixture EPUB with its own identifier, so each upload is a new book."""
    return make_epub(
        FixtureBook(
            identifier=f"urn:uuid:book-{n}",
            title=title or f"Book {n}",
            author=author,
            chapters=(FixtureChapter(paragraphs(f"Text of book {n}.")),),
        )
    )


def upload(client: TestClient, data: bytes) -> dict[str, Any]:
    """Upload `data` through the API, as the page's script does, and return the book."""
    files = {"file": ("book.epub", data, "application/epub+zip")}
    response = client.post("/api/books", files=files)
    assert response.status_code == HTTPStatus.ACCEPTED, response.text
    return response.json()


def set_status(engine: Engine, book_id: str, **values: object) -> None:
    """Put a book in a state that only the running worker passes through."""
    with engine.begin() as connection:
        connection.execute(update(books).where(books.c.id == book_id).values(**values))


def page(client: TestClient, path: str = "/") -> html.HtmlElement:
    """GET `path`, check that it is HTML, and return the parsed document."""
    response = client.get(path)
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    return html.fromstring(response.text)


def text(element: html.HtmlElement) -> str:
    """Return the text of `element` with its whitespace collapsed."""
    return " ".join(str(element.text_content()).split())


def texts(root: html.HtmlElement, selector: str) -> list[str]:
    """Return the text of each element that matches the CSS `selector`."""
    return [text(element) for element in select(root, selector)]


def cards(root: html.HtmlElement) -> list[html.HtmlElement]:
    """Return the book cards of the page, in page order."""
    return select(root, ".book-grid > article.book-card")


def card(root: html.HtmlElement, title: str) -> html.HtmlElement:
    """Return the card of the book titled `title`."""
    (found,) = [c for c in cards(root) if texts(c, ".book-card__title") == [title]]
    return found


def test_empty_library(client: TestClient) -> None:
    """With no books, GET / is the empty library of `empty.html`."""
    root = page(client)
    assert texts(root, "title") == ["Library · LibRag"]
    assert texts(root, ".site-header .wordmark") == ["LibRag"]
    assert texts(root, ".main-nav a") == ["Library", "Chat"]
    assert texts(root, '.main-nav a[aria-current="page"]') == ["Library"]
    assert texts(root, "h1.page-title") == ["Your library is empty"]
    assert texts(root, ".page-head .lede") == [
        "Add an EPUB to ask questions about it in Chat."
    ]
    assert texts(root, ".drop-zone .drop-zone__title") == ["Drop EPUB files here"]
    assert texts(root, ".drop-zone .drop-zone__hint") == [
        "or choose them from your device"
    ]
    # "Add a book" is the only action, and it sits in the drop area.
    assert texts(root, "button.button-primary") == ["Add a book"]
    assert select(root, ".drop-zone button.button-primary")
    assert not select(root, ".book-grid")
    assert not select(root, ".notices > *")


def test_books_are_listed_newest_first(
    client: TestClient, work: Callable[[], bool]
) -> None:
    """Each book has a card with cover, title, author and status, newest first."""
    upload(client, book(1, "Meditations", "Marcus Aurelius"))
    assert work()
    upload(client, book(2, "Noise", None))
    root = page(client)
    assert texts(root, "h1.page-title") == ["Your library"]
    assert texts(root, ".page-head .button-primary") == ["Add a book"]
    assert not select(root, ".drop-zone")
    assert [texts(c, ".book-card__title") for c in cards(root)] == [
        ["Noise"],
        ["Meditations"],
    ]
    noise, meditations = cards(root)
    assert texts(noise, ".book-card__author") == ["Unknown author"]
    assert texts(noise, ".status.status--queued") == ["Waiting in the queue"]
    assert texts(meditations, ".book-card__author") == ["Marcus Aurelius"]
    assert texts(meditations, ".status.status--indexed") == ["Indexed · 1 passage"]
    # The cover shows the title on a colour, and is hidden from screen readers.
    for each, title in ((noise, "Noise"), (meditations, "Meditations")):
        (cover,) = select(each, ".book-card__cover")
        assert text(cover) == title
        assert cover.get("aria-hidden") == "true"
    # Delete waits until the queued book is done.
    assert not select(noise, ".action-links")
    assert texts(meditations, ".action-links a") == ["Delete"]


def test_indexed_book_counts_its_passages(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """An indexed book shows "Indexed · N passages", and no progress bar."""
    uploaded = upload(client, book(1))
    assert work()
    set_status(engine, uploaded["id"], passages_indexed=612, passages_total=612)
    root = page(client)
    assert texts(root, ".status.status--indexed") == ["Indexed · 612 passages"]
    assert not select(root, "progress")


def test_cover_colour_comes_from_the_book_id(client: TestClient) -> None:
    """A book keeps its cover colour, and the colours vary between books."""
    for n in range(8):
        upload(client, book(n))
    colours = [
        select(c, ".book-card__cover")[0].get("class") for c in cards(page(client))
    ]
    assert all(colour.startswith("book-card__cover cover--") for colour in colours)
    assert len(set(colours)) > 1
    assert colours == [
        select(c, ".book-card__cover")[0].get("class") for c in cards(page(client))
    ]


def test_parsing_book(client: TestClient, engine: Engine) -> None:
    """A book in parsing shows "Reading the book", as in `upload-error.html`."""
    uploaded = upload(client, book(1, "Antifragile"))
    set_status(engine, uploaded["id"], status="parsing")
    status = select(card(page(client), "Antifragile"), ".status")
    assert [(s.get("class"), text(s)) for s in status] == [
        ("status status--parsing", "Reading the book")
    ]


@pytest.mark.parametrize(
    ("indexed", "total", "percent"),
    [(0, None, 0), (0, 0, 0), (63, 100, 63), (2, 3, 66), (612, 612, 100)],
)
def test_indexing_book_shows_its_progress(
    client: TestClient,
    engine: Engine,
    indexed: int,
    total: int | None,
    percent: int,
) -> None:
    """A book in indexing shows "Indexing · N%" and a progress bar with N."""
    uploaded = upload(client, book(1, "The Black Swan"))
    set_status(
        engine,
        uploaded["id"],
        status="indexing",
        passages_indexed=indexed,
        passages_total=total,
    )
    found = card(page(client), "The Black Swan")
    assert texts(found, ".status.status--indexing") == [f"Indexing · {percent}%"]
    (progress,) = select(found, "progress.progress")
    assert (progress.get("value"), progress.get("max")) == (str(percent), "100")
    assert progress.get("aria-label") == "Indexing progress"


def test_failed_book(client: TestClient, work: Callable[[], bool]) -> None:
    """A failed book shows "Failed: <error>" on a failed card."""
    no_text = FixtureBook(identifier="empty", chapters=(FixtureChapter("<p> </p>"),))
    upload(client, make_epub(no_text))
    assert work()
    (failed,) = cards(page(client))
    assert failed.get("class") == "book-card book-card--failed"
    assert select(failed, ".book-card__cover.cover--blank")
    assert texts(failed, ".status.status--failed") == [
        "Failed: No text found in the EPUB"
    ]


@pytest.mark.parametrize(
    ("count", "lede"),
    [
        (1, "One book."),
        (2, "Two books."),
        (5, "Five books."),
        (10, "Ten books."),
        (12, "12 books."),
    ],
)
def test_lede_counts_the_books(client: TestClient, count: int, lede: str) -> None:
    """The lede says how many books there are, in words up to ten."""
    for n in range(count):
        upload(client, book(n))
    assert texts(page(client), ".page-head .lede") == [
        f"{lede} Ask about any of them in Chat once they are indexed."
    ]


def test_book_grid_fragment(client: TestClient) -> None:
    """GET /library/books returns the library region of the page, without the page."""
    upload(client, book(1, "Meditations"))
    response = client.get("/library/books")
    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "<html" not in response.text
    fragment = html.fragment_fromstring(response.text)
    assert fragment.get("id") == "library"
    assert texts(fragment, ".book-card__title") == ["Meditations"]
    assert texts(fragment, ".page-head .lede") == [
        "One book. Ask about any of them in Chat once they are indexed."
    ]
    # The page embeds the same region, so a swap replaces it in place.
    (region,) = select(page(client), "#library")
    assert html.tostring(region, with_tail=False) == html.tostring(fragment)


def poll_trigger(client: TestClient) -> tuple[str | None, str | None]:
    """Return the HTMX trigger and URL of the grid fragment, on the page and alone."""
    fragment = html.fragment_fromstring(client.get("/library/books").text)
    (region,) = select(page(client), "#library")
    assert region.get("hx-trigger") == fragment.get("hx-trigger")
    return cast("str | None", fragment.get("hx-trigger")), cast(
        "str | None", fragment.get("hx-get")
    )


def test_grid_polls_while_a_book_is_in_progress(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """The fragment polls every 2 seconds while a book is queued, parsing, indexing."""
    assert poll_trigger(client) == (None, None)
    uploaded = upload(client, book(1))
    assert poll_trigger(client) == (POLL, "/library/books")
    for status in ("parsing", "indexing"):
        set_status(engine, uploaded["id"], status=status)
        assert poll_trigger(client) == (POLL, "/library/books")
    set_status(engine, uploaded["id"], status="queued")
    assert work()
    assert poll_trigger(client) == (None, None)


def test_grid_stops_polling_when_no_book_is_in_progress(
    client: TestClient, work: Callable[[], bool]
) -> None:
    """Indexed and failed books do not keep the grid polling."""
    upload(client, book(1))
    no_text = FixtureBook(identifier="empty", chapters=(FixtureChapter("<p> </p>"),))
    upload(client, make_epub(no_text))
    assert work()
    assert poll_trigger(client) == (POLL, "/library/books")
    assert work()
    assert poll_trigger(client) == (None, None)


def test_titles_are_escaped(client: TestClient) -> None:
    """A title with markup shows as text, not as HTML."""
    upload(client, book(1, "<b>Bold</b> & <script>x()</script>"))
    root = page(client)
    assert texts(root, ".book-card__title") == ["<b>Bold</b> & <script>x()</script>"]
    assert not select(root, ".book-card b")
    assert not select(root, ".book-card script")


def test_page_has_the_upload_controls(client: TestClient) -> None:
    """The page has the file picker, the drop overlay and the notices list."""
    root = page(client)
    (picker,) = select(root, 'input[type="file"]')
    assert picker.get("accept") == ".epub,application/epub+zip"
    assert picker.get("multiple") is not None
    (overlay,) = select(root, ".drop-overlay")
    assert overlay.get("hidden") is not None
    assert texts(overlay, ".drop-overlay__title") == ["Drop to add to your library"]
    assert texts(overlay, ".drop-overlay__hint") == ["EPUB files up to 50 MB each"]
    (notices,) = select(root, "ul.notices")
    assert notices.get("aria-live") == "polite"
    # The notices outlive a refresh of the grid.
    assert notices.get("id") == "notices"
    assert notices.get("hx-preserve") is not None
    assert select(root, "#library ul#notices")
    assert root.get("data-max-upload-mb") is None
    assert select(root, "body")[0].get("data-max-upload-mb") == "50"


def test_page_loads_no_external_resources(client: TestClient) -> None:
    """Every script and stylesheet is served by the app, and none loads a font."""
    root = page(client)
    sources = [s.get("src") for s in select(root, "script")]
    sheets = [link.get("href") for link in select(root, "link")]
    assert sorted(sources) == ["/static/htmx.min.js", "/static/library.js"]
    assert sheets == ["/static/app.css"]
    assert not select(root, "style, [style], iframe, img")
    for path in [*sources, *sheets]:
        assert not urlsplit(path).netloc
        response = client.get(path)
        assert response.status_code == HTTPStatus.OK, path
        assert "http://" not in response.text
        assert "https://" not in response.text
    css = client.get("/static/app.css").text
    assert "@import" not in css
    assert "@font-face" not in css
    assert "url(" not in css


def actions(found: html.HtmlElement) -> list[tuple[str, str | None, str | None]]:
    """Return each action link of a card: its text, method and URL."""
    return [
        (text(link), link.get("data-method"), link.get("data-url"))
        for link in select(found, ".action-links a")
    ]


def test_card_actions_with_the_reindex_switch_off(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """Indexed books have Delete, failed books Retry and Delete, as in `default.html`.

    Books in progress have no actions, and nothing says Reindex or out of date.
    """
    upload(client, book(1, "Thinking, Fast and Slow"))
    assert work()
    no_text = FixtureBook(
        identifier="atlas",
        title="scanned-atlas.epub",
        chapters=(FixtureChapter("<p> </p>"),),
    )
    failed = upload(client, make_epub(no_text))
    assert work()
    upload(client, book(2, "Meditations"))
    swan = upload(client, book(3, "The Black Swan"))
    set_status(engine, swan["id"], status="indexing", passages_total=10)
    noise = upload(client, book(4, "Noise"))
    set_status(engine, noise["id"], status="parsing")

    root = page(client)
    delete_link = ("Delete", None, None)
    assert actions(card(root, "Thinking, Fast and Slow")) == [delete_link]
    assert actions(card(root, "scanned-atlas.epub")) == [
        ("Retry", "POST", f"/api/books/{failed['id']}/retry"),
        delete_link,
    ]
    for title in ("Meditations", "The Black Swan", "Noise"):
        assert not select(card(root, title), ".action-links, .confirm")
    (link,) = select(card(root, "Thinking, Fast and Slow"), ".action-links a.danger")
    assert link.get("data-delete") is not None
    assert link.get("href") == "#"
    assert not select(root, ".status-note, .page-head__actions")
    assert "Reindex" not in client.get("/").text
    # The page head is the one of `default.html`: only "Add a book".
    assert texts(root, ".page-head button") == ["Add a book"]


def test_delete_asks_for_confirmation_in_the_card(
    client: TestClient, work: Callable[[], bool]
) -> None:
    """Each deletable card holds the hidden confirmation of `delete-confirm.html`."""
    uploaded = upload(client, book(1, "Noise"))
    assert work()
    (confirm,) = select(card(page(client), "Noise"), ".confirm")
    assert confirm.get("hidden") is not None
    assert confirm.get("role") == "group"
    assert confirm.get("aria-label") == "Confirm delete"
    assert texts(confirm, ".confirm__question") == [
        "Delete this book and its passages?"
    ]
    buttons = select(confirm, ".confirm__actions button")
    assert [
        (b.get("class"), text(b), b.get("data-method"), b.get("data-url"))
        for b in buttons
    ] == [
        ("button-danger", "Delete", "DELETE", f"/api/books/{uploaded['id']}"),
        ("button-quiet", "Cancel", None, None),
    ]
    assert buttons[1].get("data-cancel") is not None


def test_interrupted_book_shows_as_failed(
    client: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """A book left in indexing with its job done shows as failed, with Retry."""
    uploaded = upload(client, book(1, "Antifragile"))
    assert work()
    set_status(engine, uploaded["id"], status="indexing")
    found = card(page(client), "Antifragile")
    assert found.get("class") == "book-card book-card--failed"
    assert texts(found, ".status.status--failed") == [
        "Failed: indexing was interrupted"
    ]
    assert [name for name, _, _ in actions(found)] == ["Retry", "Delete"]


def test_reindex_switch_on_shows_out_of_date_books(
    on: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """With the switch on, the page is `reindex.html`.

    Each out-of-date book says why, every indexed book has Reindex, and the head
    has a button that reindexes the out-of-date books.
    """
    titles = ("Up to date", "Model", "Target", "Overlap", "Tokenizer")
    ids = {title: upload(on, book(n, title))["id"] for n, title in enumerate(titles)}
    for _ in titles:
        assert work()
    set_status(engine, ids["Model"], embedding_model="openai/text-embedding-3-small")
    set_status(engine, ids["Target"], passage_target_tokens=500)
    set_status(engine, ids["Overlap"], passage_overlap_tokens=80)
    set_status(engine, ids["Tokenizer"], tokenizer="o200k_base")
    swan = upload(on, book(9, "The Black Swan"))
    set_status(engine, swan["id"], status="indexing", passages_total=10)

    root = page(on)
    notes = {title: texts(card(root, title), ".status-note") for title in titles}
    assert notes == {
        "Up to date": [],
        "Model": ["Out of date: indexed with text-embedding-3-small"],
        "Target": ["Out of date: passages of 500 tokens"],
        "Overlap": ["Out of date: passage overlap of 80 tokens"],
        "Tokenizer": ["Out of date: tokenized with o200k_base"],
    }
    for title in titles:
        assert actions(card(root, title)) == [
            ("Reindex", "POST", f"/api/books/{ids[title]}/reindex"),
            ("Delete", None, None),
        ]
    assert not select(card(root, "The Black Swan"), ".action-links, .status-note")
    (head,) = select(root, ".page-head .page-head__actions")
    buttons = select(head, "button")
    assert [(b.get("class"), text(b)) for b in buttons] == [
        ("button-quiet", "Reindex 4 out-of-date books"),
        ("button-primary", "Add a book"),
    ]
    assert buttons[0].get("data-method") == "POST"
    assert buttons[0].get("data-url") == "/api/books/reindex-out-of-date"


def test_reindex_button_counts_one_book(
    on: TestClient, engine: Engine, work: Callable[[], bool]
) -> None:
    """One out-of-date book: "Reindex 1 out-of-date book"; none: no button."""
    uploaded = upload(on, book(1))
    assert work()
    root = page(on)
    assert not select(root, ".page-head__actions")
    assert texts(root, ".page-head button") == ["Add a book"]
    set_status(engine, uploaded["id"], passage_target_tokens=500)
    assert texts(page(on), ".page-head__actions .button-quiet") == [
        "Reindex 1 out-of-date book"
    ]
