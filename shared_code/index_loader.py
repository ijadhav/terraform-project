import os
from typing import List, Dict, Any, Iterable

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI
from pathlib import Path
from shared_code.settings_loader import load_local_settings

load_local_settings()


load_dotenv()


AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "terrabot-terraform-corpus")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")


def validate_settings():
    missing = []

    if not AZURE_SEARCH_ENDPOINT:
        missing.append("AZURE_SEARCH_ENDPOINT")
    if not AZURE_SEARCH_KEY:
        missing.append("AZURE_SEARCH_KEY")
    if not AZURE_SEARCH_INDEX_NAME:
        missing.append("AZURE_SEARCH_INDEX_NAME")
    if not AZURE_OPENAI_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not AZURE_OPENAI_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")
    if not AZURE_OPENAI_EMBEDDING_DEPLOYMENT:
        missing.append("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

    if missing:
        raise ValueError("Missing environment variables: " + ", ".join(missing))


def get_search_client() -> SearchClient:
    validate_settings()
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def get_embedding_client() -> AzureOpenAI:
    validate_settings()
    return AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
    )


def batch_items(items: List[Any], batch_size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def build_embedding_text(doc: Dict[str, Any]) -> str:
    parts = [
        f"repo_name: {doc.get('repo_name', '')}",
        f"cloud: {doc.get('cloud', '')}",
        f"strategy: {doc.get('strategy', '')}",
        f"doc_type: {doc.get('doc_type', '')}",
        f"path: {doc.get('path', '')}",
        f"module_name: {doc.get('module_name', '') or ''}",
        f"resource_type: {doc.get('resource_type', '') or ''}",
        f"environment_name: {doc.get('environment_name', '') or ''}",
        "",
        doc.get("content", "") or "",
    ]
    return "\n".join(parts).strip()


def get_embeddings(texts: List[str]) -> List[List[float]]:
    client = get_embedding_client()

    response = client.embeddings.create(
        model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        input=texts,
    )

    return [item.embedding for item in response.data]


def convert_chunk_to_index_doc(chunk: Dict[str, Any], embedding: List[float]) -> Dict[str, Any]:
    return {
        "id": chunk["chunk_id"],
        "repo_name": chunk.get("repo_name"),
        "cloud": chunk.get("cloud"),
        "strategy": chunk.get("strategy"),
        "doc_type": chunk.get("doc_type"),
        "path": chunk.get("path"),
        "module_name": chunk.get("module_name"),
        "resource_type": chunk.get("resource_type"),
        "environment_name": chunk.get("environment_name"),
        "is_module_definition": bool(chunk.get("is_module_definition", False)),
        "is_module_usage": bool(chunk.get("is_module_usage", False)),
        "is_value_source": bool(chunk.get("is_value_source", False)),
        "is_repo_template": bool(chunk.get("is_repo_template", False)),
        "content": chunk.get("content", ""),
        "content_vector": embedding,
        "parent_id": chunk.get("parent_id"),
        "chunk_index": chunk.get("chunk_index", 0),
    }


def prepare_index_documents(chunks: List[Dict[str, Any]], embedding_batch_size: int = 16) -> List[Dict[str, Any]]:
    prepared_docs: List[Dict[str, Any]] = []

    for batch in batch_items(chunks, embedding_batch_size):
        texts = [build_embedding_text(chunk) for chunk in batch]
        embeddings = get_embeddings(texts)

        for chunk, embedding in zip(batch, embeddings):
            prepared_docs.append(convert_chunk_to_index_doc(chunk, embedding))

    return prepared_docs


def upload_documents(index_docs: List[Dict[str, Any]], upload_batch_size: int = 100):
    client = get_search_client()

    for batch in batch_items(index_docs, upload_batch_size):
        results = client.upload_documents(documents=batch)

        failed = [r for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"Failed to upload {len(failed)} documents to Azure AI Search.")


def delete_documents_by_ids(ids: List[str], delete_batch_size: int = 100):
    client = get_search_client()

    for batch in batch_items(ids, delete_batch_size):
        docs = [{"id": doc_id} for doc_id in batch]
        results = client.delete_documents(documents=docs)

        failed = [r for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"Failed to delete {len(failed)} documents from Azure AI Search.")


def reindex_chunks(chunks: List[Dict[str, Any]], embedding_batch_size: int = 16, upload_batch_size: int = 100):
    index_docs = prepare_index_documents(
        chunks,
        embedding_batch_size=embedding_batch_size,
    )
    upload_documents(
        index_docs,
        upload_batch_size=upload_batch_size,
    )
    return {
        "uploaded_count": len(index_docs),
        "index_name": AZURE_SEARCH_INDEX_NAME,
    }