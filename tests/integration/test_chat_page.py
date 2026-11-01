# Copyright (C) 2026 Theo van Oostrum
"""HTTP tests for the Chat page at GET /chat.

The page is checked against the gallery pages in `design/pages/chat/`. Its
script's behavior is checked in the running app with the verify skill.
"""

import dataclasses
from collections.abc import Callable
from http import HTTPStatus
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from lxml import html
from sqlalchemy import Engine

from librag.main import create_app
from librag.settings import ChatModel, Settings
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
from tests.integration.test_library import (
    page,
    select,
    set_status,
    text,
    texts,
    upload,
)

DEFAULT_MODEL = "anthropic/claude-sonnet-5-5"


def fixture(n: int, title: str, author: str | None) -> FixtureBook:
    """Return a fixture book with one short chapter."""
    return FixtureBook(
        identifier=f"urn:uuid:chat-{n}",
        title=title,
        author=author,
        chapters=(FixtureChapter(paragraphs(f"Text of {title}.")),),
    )


def chat_page(client: TestClient) -> html.HtmlElement:
    """Return the parsed Chat page, after checking it is a 200 HTML page."""
    return page(client, "/chat")


def one(root: html.HtmlElement, selector: str) -> html.HtmlElement:
    """Return the one element that matches `selector`."""
    [element] = select(root, selector)
    return element


def test_no_indexed_book_disables_chat(client: TestClient, engine: Engine) -> None:
    """Without an indexed book, the page says so and the ask bar is disabled.

    A book that is still in the queue or failed does not count.
    """
    upload(client, make_epub(fixture(1, "Queued", "Ada Writer")))
    failed = upload(client, make_epub(fixture(2, "Broken", "Ada Writer")))
    set_status(engine, failed["id"], status="failed", error="Not an EPUB")
    root = chat_page(client)
    assert one(root, "body").get("class") == "chat-body"
    assert one(root, "main").get("class") == "page page--reading"
    assert texts(root, ".chat-intro__title") == ["No books are indexed yet"]
    assert texts(root, ".chat-intro__hint") == [
        "You can ask questions here once a book in your library is indexed."
    ]
    link = one(root, ".chat-intro a.button-primary")
    assert (text(link), link.get("href")) == ("Go to the Library", "/")
    form = one(root, "form.ask")
    assert form.get("class") == "ask ask--disabled"
    question = one(form, "input.ask__input")
    assert question.get("disabled") is not None
    assert question.get("placeholder") == "Add a book to start asking"
    assert one(form, "button.button-primary").get("disabled") is not None
    assert one(form, "select").get("disabled") is not None
    toggle = one(form, ".picker__toggle")
    assert text(toggle) == "Books: none ▾"
    assert toggle.get("disabled") is not None
    assert select(root, ".picker__panel input") == []
    assert one(root, ".main-nav [aria-current]").get("href") == "/chat"


def test_indexed_books_enable_chat(
    client: TestClient, index: Callable[..., None]
) -> None:
    """With indexed books, the page invites a question; the picker lists them."""
    index(
        fixture(1, "Noise", "Daniel Kahneman"),
        fixture(2, "The Black Swan", "Nassim Nicholas Taleb"),
        fixture(3, "Thinking, Fast and Slow", "Daniel Kahneman"),
        fixture(4, "Anonymous Tales", None),
    )
    upload(client, make_epub(fixture(5, "Antifragile", "Nassim Nicholas Taleb")))
    root = chat_page(client)
    assert texts(root, ".chat-intro__title") == ["Ask your library"]
    assert texts(root, ".chat-intro__hint") == [
        (
            "Answers quote the passages they come from. Pick a model and the books "
            "to search below."
        )
    ]
    assert select(root, ".chat-intro a") == []
    assert one(root, ".chat-head").get("hidden") is not None
    assert texts(root, ".chat-head .button-quiet") == ["New conversation"]
    form = one(root, "form.ask")
    assert form.get("class") == "ask"
    question = one(form, "input.ask__input")
    assert question.get("disabled") is None
    assert question.get("placeholder") == "Ask your library a question"
    assert one(form, ".ask__bar button").get("disabled") is None

    toggle = one(form, ".picker__toggle")
    assert text(toggle) == "Books: All indexed books ▾"
    assert toggle.get("aria-expanded") == "false"
    panel = one(form, ".picker__panel")
    assert panel.get("hidden") is not None
    assert texts(panel, "label") == [
        "All indexed books",
        "Daniel Kahneman",
        "Noise",
        "Thinking, Fast and Slow",
        "Nassim Nicholas Taleb",
        "The Black Swan",
        "Unknown author",
        "Anonymous Tales",
    ]
    groups = select(panel, ".picker__group")
    assert [texts(g, ".picker__author") for g in groups] == [
        ["Daniel Kahneman"],
        ["Nassim Nicholas Taleb"],
        ["Unknown author"],
    ]
    boxes = select(panel, "input")
    assert all(box.get("checked") is not None for box in boxes)
    listed = {b.get("value") for b in select(panel, ".picker__book input")}
    indexed = {
        b["id"]
        for b in client.get("/api/books").json()["books"]
        if b["status"] == "indexed"
    }
    assert listed == indexed


def test_model_select_lists_the_configured_models(settings: Settings) -> None:
    """The model select shows each configured model, with the default selected."""
    configured = dataclasses.replace(
        settings,
        chat_models=(ChatModel("a/one", "One"), ChatModel("b/two", "Two")),
        chat_default_model="b/two",
    )
    with TestClient(create_app(configured)) as client:
        options = select(chat_page(client), "form.ask select option")
    assert [
        (o.get("value"), text(o), o.get("selected") is not None) for o in options
    ] == [
        ("a/one", "One", False),
        ("b/two", "Two", True),
    ]


def test_default_models(client: TestClient) -> None:
    """By default the select offers Claude Sonnet 5.5, selected, and GPT 6.1 Terra."""
    options = select(chat_page(client), "form.ask select option")
    assert [(o.get("value"), text(o)) for o in options] == [
        (DEFAULT_MODEL, "Claude Sonnet 5.5"),
        ("openai/gpt-6.1-terra", "GPT 6.1 Terra"),
    ]
    assert options[0].get("selected") is not None


def test_page_loads_nothing_from_outside(
    client: TestClient, index: Callable[..., None]
) -> None:
    """Every script, stylesheet and font comes from the app itself."""
    index(fixture(1, "Noise", "Daniel Kahneman"))
    root = chat_page(client)
    urls = [e.get("src") for e in select(root, "script[src]")]
    urls += [e.get("href") for e in select(root, "link[href]")]
    assert "/static/chat.js" in urls
    assert all(url and not urlsplit(url).netloc for url in urls)
    for url in urls:
        assert client.get(url).status_code == HTTPStatus.OK
    css = client.get("/static/app.css").text
    assert "@import" not in css
    assert "url(" not in css
