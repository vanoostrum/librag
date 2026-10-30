# No LLM orchestration framework

The ingestion and retrieval pipelines are plain Python services that call Qdrant, LiteLLM and the reranker directly. We do not use LangChain, LlamaIndex or a similar framework: the POC exists to measure and tune each retrieval stage, and an explicit pipeline keeps every stage inspectable and testable. Add a framework only when it shows a measured advantage.
