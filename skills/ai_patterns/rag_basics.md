# RAG (Retrieval-Augmented Generation) Basics
Core idea: store text chunks with embeddings or keyword index, retrieve top-k relevant chunks for a query, inject into prompt as context.
Two failure modes: storing too much per chunk (dilutes relevance) or too little (loses context). Aim for self-contained, focused chunks (a few sentences to a paragraph).
Freshness matters: stale RAG entries can mislead the model into giving outdated answers — periodic re-indexing or expiry is worth having for fast-changing info.
