# Hybrid retrieval and fusion run inside Qdrant

Each passage is stored in Qdrant with a dense vector and a BM25 sparse vector, and Qdrant fuses the two result lists with Reciprocal Rank Fusion in one query. We chose this over a separate BM25 index (such as a search engine or an in-process library) so that one store holds all retrieval data, and so that Qdrant Cloud can replace the local Qdrant in the Vercel phase without code changes.
