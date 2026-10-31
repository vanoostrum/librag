# Copyright (C) 2026 Theo van Oostrum
"""Read an EPUB with `zipfile` and `lxml`: its metadata, chapters and paragraphs."""

import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass
from urllib.parse import unquote

from lxml import etree

NOT_READABLE = "The file is not a readable EPUB"
NO_TITLE = "The EPUB has no title"
# The upload limit counts compressed bytes, so a small zip can unpack to
# gigabytes. No file inside an EPUB may unpack to more than this.
MAX_MEMBER_BYTES = 32 * 1024 * 1024
TOO_LARGE_INSIDE = "The EPUB holds a file larger than 32 MB once unpacked"

BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "li",
        "blockquote",
        "pre",
        "dd",
        "dt",
        "td",
        "th",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
SECTION_TAGS = frozenset({"h2", "h3"})
EPUB_OPS_NS = "http://www.idpf.org/2007/ops"

# No DTDs, no entities and no network: an uploaded EPUB is untrusted input. The
# package files must be well-formed; chapters are often not, so their parser
# recovers what it can.
_STRICT = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
_LENIENT = etree.XMLParser(
    recover=True, resolve_entities=False, no_network=True, load_dtd=False
)


class EpubError(ValueError):
    """The file is not an EPUB that LibRag can read. The message says why."""


@dataclass(frozen=True)
class BookMetadata:
    """The metadata that identifies a book."""

    identifier: str | None
    title: str
    author: str | None

    @property
    def book_id(self) -> str:
        """Return the book ID: a hash of `dc:identifier`, else of title and author."""
        if self.identifier is not None:
            key = self.identifier
        else:
            key = f"{normalize(self.title).lower()}\n{normalize(self.author).lower()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Paragraph:
    """One paragraph of a chapter, with its index and the section it is in."""

    index: int
    text: str
    section: str | None


@dataclass(frozen=True)
class Chapter:
    """One spine document that has text."""

    spine_index: int
    title: str
    paragraphs: tuple[Paragraph, ...]


def normalize(text: str | None) -> str:
    """Return `text` with its whitespace collapsed to single spaces."""
    return " ".join((text or "").split())


def _local(element: etree._Element) -> str:
    """Return the tag name without its namespace; "" for comments and the like."""
    if not isinstance(element.tag, str):
        return ""
    return str(etree.QName(element).localname)


def _parse_xml(data: bytes, *, strict: bool = False) -> etree._Element:
    try:
        root = etree.fromstring(data, _STRICT if strict else _LENIENT)
    except etree.LxmlError as error:
        raise EpubError(NOT_READABLE) from error
    if not isinstance(root, etree._Element):  # noqa: SLF001 - lxml's public type
        raise EpubError(NOT_READABLE)
    return root


def _text(element: etree._Element) -> str:
    return normalize("".join(str(text) for text in element.itertext()))


@dataclass(frozen=True)
class _Package:
    archive: zipfile.ZipFile
    opf_path: str
    opf: etree._Element

    def read(self, path: str) -> bytes:
        """Return the member `path`, refusing one that unpacks to too much.

        `zipfile` stops at the size in the member's header, so checking that
        size bounds the memory that the read takes.
        """
        try:
            if self.archive.getinfo(path).file_size > MAX_MEMBER_BYTES:
                raise EpubError(TOO_LARGE_INSIDE)
            return self.archive.read(path)
        except (KeyError, zipfile.BadZipFile) as error:
            raise EpubError(NOT_READABLE) from error

    def href_path(self, href: str, base: str | None = None) -> str:
        """Return the zip path of `href`, relative to `base` (the OPF by default)."""
        directory = posixpath.dirname(base or self.opf_path)
        path = unquote(href.split("#", 1)[0])
        return posixpath.normpath(posixpath.join(directory, path))

    def children(self, parent: str) -> list[etree._Element]:
        return [
            element
            for section in self.opf
            if _local(section) == parent
            for element in section
            if isinstance(element.tag, str)
        ]


def _open(data: bytes) -> _Package:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise EpubError(NOT_READABLE) from error
    package = _Package(archive, "", etree.Element("package"))
    container = _parse_xml(package.read("META-INF/container.xml"), strict=True)
    rootfiles = [e for e in container.iter() if _local(e) == "rootfile"]
    opf_path = rootfiles[0].get("full-path", "") if rootfiles else ""
    if opf_path == "":
        raise EpubError(NOT_READABLE)
    opf = _parse_xml(package.read(opf_path), strict=True)
    if _local(opf) != "package":
        raise EpubError(NOT_READABLE)
    return _Package(archive, opf_path, opf)


def _metadata(package: _Package) -> BookMetadata:
    fields = package.children("metadata")
    unique_id = package.opf.get("unique-identifier")
    identifiers = [e for e in fields if _local(e) == "identifier" and _text(e)]
    preferred = [e for e in identifiers if e.get("id") == unique_id] or identifiers
    titles = [_text(e) for e in fields if _local(e) == "title" and _text(e)]
    authors = [_text(e) for e in fields if _local(e) == "creator" and _text(e)]
    if not titles:
        raise EpubError(NO_TITLE)
    return BookMetadata(
        identifier=_text(preferred[0]) if preferred else None,
        title=titles[0],
        author=authors[0] if authors else None,
    )


def read_metadata(data: bytes) -> BookMetadata:
    """Return the identifier, title and author of the EPUB in `data`."""
    return _metadata(_open(data))


def _nav_titles(
    package: _Package, manifest: dict[str, etree._Element]
) -> dict[str, str]:
    """Return the chapter title per zip path, from EPUB 3 nav or EPUB 2 NCX."""
    titles: dict[str, str] = {}
    navs = [
        item
        for item in manifest.values()
        if "nav" in (item.get("properties") or "").split()
    ]
    if navs:
        nav_path = package.href_path(navs[0].get("href", ""))
        root = _parse_xml(package.read(nav_path))
        for nav in (e for e in root.iter() if _local(e) == "nav"):
            if nav.get(f"{{{EPUB_OPS_NS}}}type") != "toc":
                continue
            for link in (e for e in nav.iter() if _local(e) == "a"):
                path = package.href_path(link.get("href", ""), nav_path)
                titles.setdefault(path, _text(link))
        return titles
    spine = [e for e in package.opf if _local(e) == "spine"]
    toc_id = spine[0].get("toc") if spine else None
    if toc_id is not None and toc_id in manifest:
        ncx_path = package.href_path(manifest[toc_id].get("href", ""))
        root = _parse_xml(package.read(ncx_path))
        for point in (e for e in root.iter() if _local(e) == "navPoint"):
            label = next((e for e in point if _local(e) == "navLabel"), None)
            content = next((e for e in point if _local(e) == "content"), None)
            if label is not None and content is not None:
                path = package.href_path(content.get("src", ""), ncx_path)
                titles.setdefault(path, _text(label))
    return titles


def _leaf_blocks(body: etree._Element) -> list[etree._Element]:
    """Return the block elements that hold no other block, in document order."""
    return [
        element
        for element in body.iter()
        if _local(element) in BLOCK_TAGS
        and not any(_local(child) in BLOCK_TAGS for child in element.iterdescendants())
    ]


def _chapter(spine_index: int, data: bytes, nav_title: str | None) -> Chapter | None:
    root = _parse_xml(data)
    body = next((e for e in root.iter() if _local(e) == "body"), root)
    section: str | None = None
    first_heading: str | None = None
    found: list[Paragraph] = []
    for block in _leaf_blocks(body):
        text = _text(block)
        if not text:
            continue
        tag = _local(block)
        if tag in HEADING_TAGS:
            first_heading = first_heading or text
            if tag in SECTION_TAGS:
                section = text
            continue
        found.append(Paragraph(index=len(found), text=text, section=section))
    if not found:
        return None
    title = nav_title or first_heading or f"Chapter {spine_index + 1}"
    return Chapter(spine_index=spine_index, title=title, paragraphs=tuple(found))


def read_chapters(data: bytes) -> list[Chapter]:
    """Return the chapters of the EPUB in `data` that have text, in spine order."""
    package = _open(data)
    manifest = {
        item.get("id", ""): item
        for item in package.children("manifest")
        if _local(item) == "item"
    }
    titles = _nav_titles(package, manifest)
    chapters: list[Chapter] = []
    spine = package.children("spine")
    for spine_index, itemref in enumerate(e for e in spine if _local(e) == "itemref"):
        item = manifest.get(itemref.get("idref", ""))
        if item is None:
            raise EpubError(NOT_READABLE)
        path = package.href_path(item.get("href", ""))
        chapter = _chapter(spine_index, package.read(path), titles.get(path))
        if chapter is not None:
            chapters.append(chapter)
    return chapters
