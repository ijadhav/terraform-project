# Terrabot VS Code Integration

Terrabot registers a VS Code chat participant named `@terrabot` and lets users make repo-aware infrastructure requests from the VS Code Chat/terminal experience.

## Local development

```bash
cd TerraVS
python3 -m pip install -e .
cd vscode-terrabot
npm install
npm run compile
code --new-window --extensionDevelopmentPath="$PWD" /path/to/terraform/repo
```

Use VS Code Chat:

```text
@terrabot create an Azure Linux VM in npr following this repo's patterns
@terrabot /explain-workflow how does this repo deploy Terraform?
```

## Hosted production mode

Set these VS Code settings for users or at the organization profile level:

```json
{
  "terrabot.generatorUrl": "https://<terrabot-function-app>.azurewebsites.net",
  "terrabot.apiToken": "<optional-token-if-your-backend-requires-it>"
}
```

When `terrabot.generatorUrl` is set, the extension collects a bounded repository context from the open workspace and posts it to:

- `POST /api/vscode/scan`
- `POST /api/vscode/explain-workflow`
- `POST /api/vscode/ask`

The Azure Functions backend keeps using the existing Terrabot Azure AI Foundry agent. The local CLI remains available as a fallback when `terrabot.generatorUrl` is empty.

## Package

```bash
cd TerraVS/vscode-terrabot
npm install
npm run compile
npx @vscode/vsce package
```

Publish the resulting `.vsix` through your internal VS Code Marketplace / Extension Gallery or distribute it with your enterprise device-management tooling.
