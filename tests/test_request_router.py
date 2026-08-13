from shared_code.request_router import route_request


def test_chat_request():
    d = route_request("What is Terraform state drift?")
    assert d.request_type == "chat"


def test_aws_request():
    d = route_request("Create an S3 bucket in dev aws")
    assert d.request_type == "infra"
    assert d.cloud == "aws"
    assert d.workflow == "aws_module_consumer"


def test_azure_consumer_request():
    d = route_request("Add an Azure storage account in prd")
    assert d.request_type == "infra"
    assert d.cloud == "azure"
    assert d.workflow == "azure_consumer_generation"


def test_azure_module_repo_request():
    d = route_request("Create a new reusable Azure module repo for service bus in prd")
    assert d.request_type == "infra"
    assert d.cloud == "azure"
    assert d.workflow == "azure_module_repo_creation"


def test_missing_cloud():
    d = route_request("Create a database in prd")
    assert d.request_type == "infra"
    assert d.workflow == "clarification_required"