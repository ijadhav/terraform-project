import os
import json

from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

def load_local_settings():
    settings_path = Path(__file__).resolve().parents[1] / "local.settings.json"

    if not settings_path.exists():
        return

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    values = data.get("Values", {})

    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = str(value)


load_local_settings()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "terrabot-terraform-corpus")
EMBEDDING_DIMENSIONS = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))


def validate_settings():
    missing = []
    if not AZURE_SEARCH_ENDPOINT:
        missing.append("AZURE_SEARCH_ENDPOINT")
    if not AZURE_SEARCH_KEY:
        missing.append("AZURE_SEARCH_KEY")
    if not AZURE_SEARCH_INDEX_NAME:
        missing.append("AZURE_SEARCH_INDEX_NAME")

    if missing:
        raise ValueError("Missing environment variables: " + ", ".join(missing))


def build_index() -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="repo_name", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="cloud", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="strategy", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="doc_type", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="path", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="module_name", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="resource_type", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SearchableField(name="environment_name", type=SearchFieldDataType.String, filterable=True, retrievable=True),

        SimpleField(name="is_module_definition", type=SearchFieldDataType.Boolean, filterable=True, retrievable=True),
        SimpleField(name="is_module_usage", type=SearchFieldDataType.Boolean, filterable=True, retrievable=True),
        SimpleField(name="is_value_source", type=SearchFieldDataType.Boolean, filterable=True, retrievable=True),
        SimpleField(name="is_repo_template", type=SearchFieldDataType.Boolean, filterable=True, retrievable=True),

        SearchableField(name="content", type=SearchFieldDataType.String, retrievable=True),

        SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True, retrievable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, retrievable=True),

        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="content-vector-profile",
            hidden=True,
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="content-hnsw"
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="content-vector-profile",
                algorithm_configuration_name="content-hnsw",
            )
        ],
    )

    return SearchIndex(
        name=AZURE_SEARCH_INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
    )


def create_or_update_index():
    validate_settings()

    client = SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )

    index = build_index()
    result = client.create_or_update_index(index)
    return result


def create_or_update_repository_context_index():
    # Reuse the same Azure AI Search service/embedding stack for durable
    # repository knowledge. A dedicated index is intentional because source
    # chunks and repository decisions have different lifecycle/version fields.
    from shared_code.repository_context import ensure_repository_context_index

    return ensure_repository_context_index(force=True)


if __name__ == "__main__":
    created = create_or_update_index()
    print(f"Index ready: {created.name}")
    context_index = create_or_update_repository_context_index()
    print(f"Repository context index ready: {context_index}")
