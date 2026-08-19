from pathlib import Path

from shared_code.corpus_builder import collect_repo_documents
from shared_code.chunkers import chunk_documents
from shared_code.index_loader import reindex_chunks


def main():
    base_dir = Path(__file__).resolve().parents[1]

    docs = collect_repo_documents(str(base_dir))
    print(f"Collected documents: {len(docs)}")

    chunks = chunk_documents(docs)
    print(f"Prepared chunks: {len(chunks)}")

    result = reindex_chunks(chunks)
    print(result)


if __name__ == "__main__":
    main()