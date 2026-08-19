## Install the Terrabot VS Code Extension

1. Download the Terrabot `.vsix` extension file.

2. Open Visual Studio Code.

3. Install **Extension** :

   * Click Cmd + Shift + P - 
   * Select Extensions: Install from VSIX

6. Select the downloaded Terrabot `.vsix` file.

7. Wait for the installation to complete.

8. Reload VS Code when prompted. :
    * Click Cmd + Shift + P -  
    * Select Developer : Reload Window 

## Open Terrabot Chat

1. Open the Terraform repository or project folder in VS Code.

2. Open the VS Code Chat panel:

   * Click the Chat icon in the sidebar, or
   * Open the Command Palette ( Cmd + Shift + P) and select **Chat: Open Chat**.

3. In the chat input, type:

   `@terrabot` *prompt*

4. Add your request after the agent tag.

## Example prompts

`@terrabot explain how this Terraform repository is structured`

`@terrabot create a storage account in the dev environment`

`@terrabot update the existing VM size to Standard_D4s_v5`

`@terrabot create a GitHub branch for these changes`

`@terrabot raise a pull request for the current changes`

5. Review the response and any proposed file changes.

6. Apply or accept the changes from the VS Code diff view.

7. Run the validation commands suggested by Terrabot before committing the changes.

Terrabot uses the currently opened VS Code workspace as its repository context, so users should open the repository root before sending prompts.

## Centralized repository context

Durable cross-user repository knowledge is implemented in `repository_context.py` and stored in Azure AI Search. It intentionally stores only evidence-validated repository conclusions, not conversation transcripts/summaries. See `docs/repository_context.md`.
