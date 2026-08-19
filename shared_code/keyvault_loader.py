import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


SECRET_ENV_MAP = {
    "github-token": "GITHUB_TOKEN",
    "azdo-pat": "AZDO_PAT",
    "azure-openai-api-key": "AZURE_OPENAI_API_KEY",
    "azure-search-key": "AZURE_SEARCH_KEY",
    "jira-api-token": "JIRA_API_TOKEN",
    "okta-client-secret": "OKTA_CLIENT_SECRET",

}


def load_keyvault_secrets():
    vault_url = os.getenv("KEY_VAULT_URL")

    if not vault_url:
        return

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)

    for secret_name, env_name in SECRET_ENV_MAP.items():
        if os.getenv(env_name):
            continue

        try:
            os.environ[env_name] = client.get_secret(secret_name).value
        except Exception as exc:
            print(f"Key Vault secret not loaded: {secret_name} -> {env_name}: {exc}")