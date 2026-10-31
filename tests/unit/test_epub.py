# Copyright (C) 2026 Theo van Oostrum
"""The EPUB reader's chapters and source locations. No route shows them yet."""

import io
import zipfile

import pytest

from librag.epub import Chapter, EpubError, Paragraph, read_chapters
from tests.epubs import (
    FixtureBook,
    FixtureChapter,
    Navigation,
    make_epub,
    paragraphs,
    replace_member,
)


def read(*chapters: FixtureChapter, navigation: Navigation = "nav") -> list[Chapter]:
    """Return the chapters that the reader finds in a fixture EPUB."""
    return read_chapters(
        make_epub(FixtureBook(chapters=chapters, navigation=navigation))
    )


@pytest.mark.parametrize("navigation", ["nav", "ncx"])
def test_chapter_title_comes_from_the_navigation(navigation: Navigation) -> None:
    """EPUB 3 nav and EPUB 2 NCX titles name the chapters."""
    chapters = read(
        FixtureChapter("<h1>Heading</h1>" + paragraphs("Text."), nav_title="Nav title"),
        navigation=navigation,
    )
    assert [c.title for c in chapters] == ["Nav title"]


def test_chapter_title_falls_back_to_the_first_heading() -> None:
    """Without a navigation entry, the first heading names the chapter."""
    chapters = read(
        FixtureChapter("<h2>Opening</h2>" + paragraphs("Text.")), navigation="none"
    )
    assert [c.title for c in chapters] == ["Opening"]


def test_chapter_title_falls_back_to_its_number() -> None:
    """Without navigation or heading, a chapter is called Chapter <n>."""
    chapters = read(
        FixtureChapter(paragraphs("One.")),
        FixtureChapter(paragraphs("Two.")),
        navigation="none",
    )
    assert [(c.spine_index, c.title) for c in chapters] == [
        (0, "Chapter 1"),
        (1, "Chapter 2"),
    ]


def test_paragraphs_have_index_and_section() -> None:
    """Paragraphs are numbered per chapter and carry the nearest h2 or h3."""
    body = (
        "<h1>Title</h1><p>Intro.</p><h2>Part A</h2><p>A one.</p>"
        "<h4>Minor</h4><p>A two.</p><h3>Part B</h3><div><p>B one.</p></div>"
    )
    [chapter] = read(FixtureChapter(body, nav_title="T"))
    assert chapter.paragraphs == (
        Paragraph(index=0, text="Intro.", section=None),
        Paragraph(index=1, text="A one.", section="Part A"),
        Paragraph(index=2, text="A two.", section="Part A"),
        Paragraph(index=3, text="B one.", section="Part B"),
    )


def test_paragraph_text_is_whitespace_collapsed() -> None:
    """Inline markup is kept as text, and whitespace is collapsed."""
    [chapter] = read(
        FixtureChapter("<p>  A <em>quiet</em>\n   morning.<!-- note --></p>")
    )
    assert [p.text for p in chapter.paragraphs] == ["A quiet morning."]


def test_empty_spine_documents_are_still_counted() -> None:
    """A spine document without text gives no chapter but keeps the spine index."""
    chapters = read(
        FixtureChapter("<p> </p>", nav_title="Cover"),
        FixtureChapter(paragraphs("Text."), nav_title="One"),
    )
    assert [(c.spine_index, c.title) for c in chapters] == [(1, "One")]


def test_landmarks_nav_is_not_the_table_of_contents() -> None:
    """Only the nav with epub:type toc names chapters."""
    epub = make_epub(
        FixtureBook(chapters=(FixtureChapter(paragraphs("Text."), nav_title="Real"),))
    )
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><body>'
        '<nav epub:type="landmarks"><a href="text/ch1.xhtml">Start here</a></nav>'
        '<nav epub:type="toc"><a href="text/ch1.xhtml#x">Real</a></nav>'
        "</body></html>"
    )
    epub = replace_member(epub, "OEBPS/nav.xhtml", nav.encode())
    assert [c.title for c in read_chapters(epub)] == ["Real"]


def test_ncx_point_without_label_is_skipped() -> None:
    """An NCX navPoint without a label leaves the title to the heading."""
    epub = make_epub(
        FixtureBook(
            chapters=(FixtureChapter("<h1>Heading</h1><p>Text.</p>", nav_title="N"),),
            navigation="ncx",
        )
    )
    ncx = (
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
        '<navPoint id="p1"><content src="text/ch1.xhtml"/></navPoint>'
        "</navMap></ncx>"
    )
    epub = replace_member(epub, "OEBPS/toc.ncx", ncx.encode())
    assert [c.title for c in read_chapters(epub)] == ["Heading"]


@pytest.mark.parametrize(
    ("member", "content"),
    [
        ("OEBPS/text/ch1.xhtml", b""),
        ("OEBPS/text/ch1.xhtml", b"garbage"),
    ],
    ids=["empty-chapter", "garbage-chapter"],
)
def test_broken_member_raises(member: str, content: bytes | None) -> None:
    """An empty or unparsable chapter raises EpubError."""
    with pytest.raises(EpubError, match="not a readable EPUB"):
        read_chapters(replace_member(make_epub(), member, content))


def test_spine_item_missing_from_the_manifest_raises() -> None:
    """A spine itemref without a manifest item raises EpubError."""
    epub = make_epub()
    with zipfile.ZipFile(io.BytesIO(epub)) as archive:
        opf = archive.read("OEBPS/content.opf").replace(b'idref="ch1"', b'idref="x"')
    with pytest.raises(EpubError, match="not a readable EPUB"):
        read_chapters(replace_member(epub, "OEBPS/content.opf", opf))
