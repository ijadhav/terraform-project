from shared_code import primary_context


def test_select_repo_docs_resolution():
    assert primary_context.select_repo_docs(repo_target="tf-azure-hub") == ["tf-azure-hub.md"]
    assert primary_context.select_repo_docs(repo_target="tf-devops") == ["tf-devops.md"]
    assert primary_context.select_repo_docs(cloud="azure") == ["tf-azure-hub.md"]
    assert primary_context.select_repo_docs(cloud="aws") == ["tf-devops.md"]
    # Unknown scope falls back to both so generation stays grounded.
    assert set(primary_context.select_repo_docs()) == {"tf-azure-hub.md", "tf-devops.md"}


def test_prompt_keyword_resolution():
    docs = primary_context.select_repo_docs(prompt="add an aws redshift module")
    assert docs == ["tf-devops.md"]
    docs = primary_context.select_repo_docs(prompt="create an azurerm storage account")
    assert docs == ["tf-azure-hub.md"]


def test_load_primary_context_azure_loaded():
    result = primary_context.load_primary_terraform_context(
        cloud="azure", environment="npr-int", prompt="disable create_cloudamqp in npr"
    )
    assert result["loaded"] is True
    assert "terraform-generation-rules.md" in result["sources"]
    assert "tf-azure-hub.md" in result["sources"]
    assert result["block"]
    # Precedence statement is always present and live-repo-first.
    assert "CONTEXT PRECEDENCE" in result["block"]
    assert "live repository always wins" in result["block"]
    assert "npr-int" in result["block"]


def test_load_primary_context_precedence_constant():
    result = primary_context.load_primary_terraform_context(cloud="aws")
    assert result["precedence"] == primary_context.PRECEDENCE_TEXT
    assert "tf-devops.md" in result["sources"]
