# A book's identity comes from its metadata; replacing a book means delete and upload

A book's ID comes from the EPUB's `dc:identifier`, or from its title and author when the identifier is missing. Passage IDs derive from the book ID and the passage's position, so indexing is deterministic and a reindex overwrites instead of duplicating. An upload of a book that is already in the library is refused: the user deletes the book first and uploads the new file. The file's content hash only detects a duplicate upload. We dropped book versions: delete and upload covers replacement, and versions added states that the POC does not need.

## Consequences

Each book stores the index configuration that indexed it, and its passages' text apart from their vectors. A reindex rebuilds a book from its stored EPUB, so a retrieval experiment never needs a new upload. A change to the embedding settings re-embeds the stored passages without a new parse. Only a change to the passage settings (size, overlap) parses the EPUB again.
