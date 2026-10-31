# Copyright (C) 2026 Theo van Oostrum
"""Write tiny EPUB files for the tests, so the repo holds no binary fixtures."""

import io
import zipfile
from dataclasses import dataclass, field
from typing import Literal
from xml.sax.saxutils import escape

Navigation = Literal["nav", "ncx", "none"]


@dataclass(frozen=True)
class FixtureChapter:
    """One spine document: its XHTML body, and its title in the navigation."""

    body: str
    nav_title: str | None = None


@dataclass(frozen=True)
class FixtureBook:
    """The metadata and chapters of a fixture EPUB."""

    title: str | None = "A Tiny Book"
    author: str | None = "Ada Writer"
    identifier: str | None = "urn:uuid:5f0c7c6e-0000-4000-8000-000000000001"
    chapters: tuple[FixtureChapter, ...] = field(
        default_factory=lambda: (
            FixtureChapter(
                "<h1>The Start</h1><p>It was a quiet morning.</p>"
                "<p>The library opened at nine.</p>",
                nav_title="The Start",
            ),
        )
    )
    navigation: Navigation = "nav"


def paragraphs(*texts: str) -> str:
    """Return XHTML paragraphs for `texts`."""
    return "".join(f"<p>{escape(text)}</p>" for text in texts)


def _chapter_xhtml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>x</title></head><body>{body}</body></html>"
    )


def _nav_xhtml(book: FixtureBook) -> str:
    items = "".join(
        f'<li><a href="text/ch{n}.xhtml">{escape(chapter.nav_title)}</a></li>'
        for n, chapter in enumerate(book.chapters, start=1)
        if chapter.nav_title is not None
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>'
        f'</head><body><nav epub:type="toc"><ol>{items}</ol></nav></body></html>'
    )


def _ncx(book: FixtureBook) -> str:
    points = "".join(
        f'<navPoint id="p{n}"><navLabel><text>{escape(chapter.nav_title)}</text>'
        f'</navLabel><content src="text/ch{n}.xhtml#top"/></navPoint>'
        for n, chapter in enumerate(book.chapters, start=1)
        if chapter.nav_title is not None
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f"<navMap>{points}</navMap></ncx>"
    )


def _opf(book: FixtureBook) -> str:
    metadata = []
    if book.identifier is not None:
        metadata.append(f'<dc:identifier id="bookid">{escape(book.identifier)}')
        metadata[-1] += "</dc:identifier>"
    if book.title is not None:
        metadata.append(f"<dc:title>{escape(book.title)}</dc:title>")
    if book.author is not None:
        metadata.append(f"<dc:creator>{escape(book.author)}</dc:creator>")
    manifest = [
        f'<item id="ch{n}" href="text/ch{n}.xhtml" media-type="application/xhtml+xml"/>'
        for n in range(1, len(book.chapters) + 1)
    ]
    spine_toc = ""
    if book.navigation == "nav":
        manifest.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>'
        )
    elif book.navigation == "ncx":
        manifest.append(
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        )
        spine_toc = ' toc="ncx"'
    spine = "".join(
        f'<itemref idref="ch{n}"/>' for n in range(1, len(book.chapters) + 1)
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"{''.join(metadata)}</metadata>"
        f"<manifest>{''.join(manifest)}</manifest>"
        f"<spine{spine_toc}>{spine}</spine></package>"
    )


CONTAINER_XML = (
    '<?xml version="1.0"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)


def make_epub(book: FixtureBook | None = None) -> bytes:
    """Return the bytes of an EPUB file for `book`."""
    book = book or FixtureBook()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as epub:
        epub.writestr(
            "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        epub.writestr("META-INF/container.xml", CONTAINER_XML)
        epub.writestr("OEBPS/content.opf", _opf(book))
        for n, chapter in enumerate(book.chapters, start=1):
            epub.writestr(f"OEBPS/text/ch{n}.xhtml", _chapter_xhtml(chapter.body))
        if book.navigation == "nav":
            epub.writestr("OEBPS/nav.xhtml", _nav_xhtml(book))
        elif book.navigation == "ncx":
            epub.writestr("OEBPS/toc.ncx", _ncx(book))
    return buffer.getvalue()


def replace_member(epub: bytes, name: str, content: bytes | None) -> bytes:
    """Return `epub` with the member `name` replaced by `content`, or removed."""
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(epub)) as source,
        zipfile.ZipFile(buffer, "w") as target,
    ):
        for item in source.infolist():
            if item.filename != name:
                target.writestr(item, source.read(item))
            elif content is not None:
                target.writestr(item, content)
    return buffer.getvalue()
