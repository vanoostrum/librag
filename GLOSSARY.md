# LibRag

LibRag makes a personal library of books available to an AI assistant. It indexes the books and answers questions with passages from them, with citations.

## Library

**Library**:
All books that one user has added to LibRag.
_Avoid_: Collection, corpus, knowledge base

**Book**:
One work in the library, identified by its EPUB metadata, with its title, author and structure.
_Avoid_: Document, file

**Passage**:
A short, continuous piece of a book's text within one chapter or section. It is the unit that LibRag indexes, retrieves and cites.
_Avoid_: Chunk, snippet, fragment

**Source location**:
Where a passage sits in its book: chapter, section, and position.
_Avoid_: Page, offset

**Ingestion job**:
The work of turning one book's EPUB into indexed passages, with a status that the user can see.
_Avoid_: Task, import

**Index configuration**:
The settings and model versions that produced a book's indexed passages. A change to it needs a reindex.
_Avoid_: Index settings

**Reindex**:
Rebuild the indexed passages of one book, without changing the other books.
_Avoid_: Refresh, rebuild

**Out of date**:
A book whose index configuration differs from the current settings. Search cannot find it, or finds passages cut differently, until it is reindexed.
_Avoid_: Stale, outdated index

**Interrupted**:
A book whose ingestion stopped without a result: it is left in parsing or indexing with no job to finish it. The user retries it.
_Avoid_: Stuck, hung

**Contextual enrichment**:
A short context line that an LLM writes for a passage at indexing time, indexed with the passage but kept apart from its original text.
_Avoid_: Augmentation, annotation

## Questions and answers

**Question**:
What the user asks in chat, in natural language.
_Avoid_: Prompt, query (for the user's text)

**Search query**:
The text that retrieval searches with: the question itself, or a standalone rewrite of it that needs no earlier turns.
_Avoid_: Rewritten prompt

**Retrieval**:
Finding and ranking the passages for a search query, without the LLM.
_Avoid_: Search (as a noun for the pipeline)

**Context**:
The passages that retrieval selects and sends to the LLM with the question.
_Avoid_: Evidence set, prompt context

**Answer**:
The LLM's reply to a question. It separates claims from the books, synthesis of book content, and general knowledge.
_Avoid_: Response, completion

**Citation**:
A reference in an answer to one passage in the context.
_Avoid_: Source, reference, footnote

**Conversation**:
The turns of one chat in the page, from the first question until "New conversation" or a reload. It is not saved.
_Avoid_: Session, thread, chat history

**Turn**:
One question and its answer within a conversation.
_Avoid_: Message, exchange

**Diagnostics**:
The record of each retrieval stage for one question: search queries, candidates, scores, context, model, tokens, latency and cost.
_Avoid_: Trace, debug info

## Evaluation

**Evaluation set**:
Questions with the passages and facts that a good answer needs, used to measure retrieval and answer quality.
_Avoid_: Test set, benchmark, golden set

**Evidence quote**:
A sentence from a book that a good answer to an evaluation question needs. Retrieval finds it when a passage contains it.
_Avoid_: Gold passage, ground truth

**Live run**:
A run of the e2e suite against the real AI providers, started by hand, with a cost cap.
_Avoid_: Live test, integration run
