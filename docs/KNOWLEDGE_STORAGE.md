# Knowledge Storage
- Knowledge lives in: data/rag_store.db (table chunks, FTS5 index chunks_fts)
- data/knowledge/ is empty by design
- config keys knowledge_root / knowledge_index feed assert_kerros_paths()
- Do not repoint them at ./data or rag_store.db
- Evidence: chunks=7, chunks_fts=7, db=36864 bytes (2026-09-11)
