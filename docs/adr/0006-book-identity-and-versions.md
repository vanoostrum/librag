# A book's identity comes from its metadata, its version from its content

A book's ID comes from the EPUB's `dc:identifier`, or from its title and author when the identifier is missing. Its version is the content hash of the EPUB file, and passage IDs derive from the book ID, the version and the passage's position, so indexing is deterministic. Each book version stores the index configuration that indexed it. Uploading a file with a known book ID and a new hash replaces the old version. Uploading the same hash when the index configuration has not changed does nothing. We chose metadata over the file hash as the identity so that a corrected edition of a book replaces the old one instead of sitting next to it as a duplicate.

## Consequences

The passages' text is stored apart from their vectors. A change to the embedding settings re-embeds the stored passages without a new parse of the EPUB. Only a change to the passage settings (size, overlap) needs a new parse.
