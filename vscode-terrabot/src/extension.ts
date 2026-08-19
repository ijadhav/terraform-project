/**
 * vscode-terrabot/src/extension.ts
 * ==================================
 * Steps 6, 7, 8 of the Terrabot prototype wiring guide.
 *
 * Changes from the original:
 *
 * Step 6 — askInfrastructure now returns void and applies generated files
 *   directly to the workspace via vscode.WorkspaceEdit instead of showing
 *   a virtual diff document.  A new applyGeneratedFiles() helper handles
 *   create / modify / delete operations.
 *
 * Step 7 — applyGeneratedFiles opens the SCM diff panel immediately after
 *   applying edits and offers a "Run Validation" action that opens a
 *   terminal and runs the validation_commands returned by the backend
 *   (e.g. terraform validate, tflint).
 *
 * Step 8 — registerChatParticipant is rewritten so @terrabot calls
 *   /api/generate and applies files via the same applyGeneratedFiles()
 *   helper, giving chat, Command Palette, and CLI one shared pipeline.
 *
 * Step 9 — Thread continuity: one Foundry conversation per chat session.
 *   The backend returns thread_id; we store it and send it back on every
 *   follow-up so the agent remembers earlier prompts, its own questions,
 *   and the user's answers. Reset on new session or workspace switch.
 *
 * Step 10 — Prioritized context collection: open editor tabs and files whose
 *   paths match prompt keywords are always included in the scan, before the
 *   general glob walk fills the remaining MAX_FILES budget. Fixes large-repo
 *   cases where the relevant module lost the 120-file lottery even while
 *   open in the editor.
 */

import * as vscode from "vscode";
import { spawn } from "child_process";
import * as https from "https";
import * as http from "http";
import * as path from "path";
import * as fs from "fs/promises";

const MAX_FILE_BYTES = 64 * 1024;
const MAX_FILES = 120;
const GITHUB_BASE_BRANCH = "main";

const DEFAULT_AI_ENDPOINT = "https://terrabot-ai.azurewebsites.net/api/generate";

// ── Step 9: session thread state ─────────────────────────────────────────────
// One Foundry conversation per VS Code chat session. Empty chat history means
// the user started a new chat (or hit Start Over), so we drop the old thread.
// A workspace switch mid-session also resets it so a new repo never inherits
// the previous repo's conversation.
let currentThreadId = "";
let currentThreadRoot = "";

// Local PR continuity state. Infrastructure generation only changes the
// workspace. Nothing is committed or pushed until the user explicitly asks
// for a PR operation.
let currentWorkspacePrBranch = "";
let currentWorkspacePrUrl = "";
let extensionContext: vscode.ExtensionContext | undefined;

const GITHUB_PAT_SECRET_KEY = "terrabot.githubToken";

type GitProgressReporter = (message: string) => void;


type PreparedGitTarget = {
  branch: string;
  notes: string[];
  mode: "new" | "current" | "existing-pr";
  prTarget?: "existing" | "new" | "normal";
};

function reportGitStep(notes: string[], reporter: GitProgressReporter | undefined, message: string): void {
  notes.push(message);
  reporter?.(message);
}

function resetThreadIfNeeded(root: string, historyLength: number): void {
  if (historyLength === 0 || root !== currentThreadRoot) {
    currentThreadId = "";
    currentThreadRoot = root;
  }
}

// ── config helpers ────────────────────────────────────────────────────────────

interface GitRepository {
  rootUri: vscode.Uri;
}

interface GitApi {
  repositories: GitRepository[];
}

async function getWorkspaceRoot(): Promise<string> {
  const gitExtension = vscode.extensions.getExtension("vscode.git");

  if (gitExtension) {
    if (!gitExtension.isActive) {
      await gitExtension.activate();
    }

    const gitApi: GitApi | undefined =
      gitExtension.exports?.getAPI?.(1);

    const activeUri =
      vscode.window.activeTextEditor?.document.uri;

    if (gitApi?.repositories?.length) {
      if (activeUri?.scheme === "file") {
        const matchingRepo = gitApi.repositories
          .filter(repo =>
            activeUri.fsPath === repo.rootUri.fsPath ||
            activeUri.fsPath.startsWith(
              `${repo.rootUri.fsPath}${path.sep}`
            )
          )
          .sort(
            (left, right) =>
              right.rootUri.fsPath.length -
              left.rootUri.fsPath.length
          )[0];

        if (matchingRepo) {
          return matchingRepo.rootUri.fsPath;
        }
      }

      if (gitApi.repositories.length === 1) {
        return gitApi.repositories[0].rootUri.fsPath;
      }
    }
  }

  // CLI fallback supports opening a parent folder containing the repository.
  const activeDirectory =
    vscode.window.activeTextEditor?.document.uri.fsPath
      ? path.dirname(
          vscode.window.activeTextEditor.document.uri.fsPath
        )
      : vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

  if (!activeDirectory) {
    throw new Error(
      "Open a Git repository before using Terrabot."
    );
  }

  const repositoryRoot = await runCommandOnce(
    "git",
    [
      "-C",
      activeDirectory,
      "rev-parse",
      "--show-toplevel",
    ],
    activeDirectory,
  );

  if (!repositoryRoot.trim()) {
    throw new Error(
      `Terrabot could not locate a Git repository from ${activeDirectory}.`
    );
  }

  return repositoryRoot.trim();
}

function getConfig<T>(name: string, fallback: T): T {
  const value = vscode.workspace.getConfiguration("terrabot").get<T>(name);
  return value === undefined || value === null || value === "" ? fallback : value;
}

function getCliPath(): string {
  return getConfig<string>("cliPath", "terrabot");
}

function normalizeEndpoint(value: string): string {
  return value.trim().replace(/\/$/, "");
}

function getAiEndpoint(): string {
  const configuredEndpoint = getConfig<string>(
    "aiEndpoint",
    process.env.TERRABOT_AI_ENDPOINT || DEFAULT_AI_ENDPOINT
  );
  return normalizeEndpoint(configuredEndpoint);
}

function getBackendBaseUrl(): string {
  const endpoint = getAiEndpoint();
  return endpoint.replace(/\/api\/generate$/, "").replace(/\/generate$/, "");
}

function getApiToken(): string {
  return getConfig<string>("apiToken", process.env.TERRABOT_API_TOKEN || "").trim();
}

async function getStoredGitHubToken(): Promise<string> {
  return (await extensionContext?.secrets.get(GITHUB_PAT_SECRET_KEY) || "").trim();
}

async function connectGitHubAccount(): Promise<{ token: string; account: string; source: "vscode" | "pat" }> {
  try {
    const session = await vscode.authentication.getSession(
      "github",
      ["repo", "read:user"],
      { createIfNone: true },
    );
    if (session?.accessToken) {
      return { token: session.accessToken, account: session.account.label, source: "vscode" };
    }
  } catch {
    // Fall through to an explicitly supplied PAT.
  }

  const stored = await getStoredGitHubToken();
  if (stored) {
    const user = await githubJson<{ login: string }>("GET", "/user", stored);
    return { token: stored, account: user.login, source: "pat" };
  }

  const choice = await vscode.window.showInformationMessage(
    "Terrabot needs your GitHub account to push branches and create pull requests.",
    { modal: true },
    "Enter GitHub token",
  );
  if (choice !== "Enter GitHub token") {
    throw new Error("GitHub authentication was cancelled.");
  }

  const token = (await vscode.window.showInputBox({
    title: "Connect Terrabot to GitHub",
    prompt: "Enter a fine-grained personal access token with Contents: Read and write and Pull requests: Read and write for this repository.",
    password: true,
    ignoreFocusOut: true,
  }) || "").trim();
  if (!token) {
    throw new Error("A GitHub token was not provided.");
  }
  const user = await githubJson<{ login: string }>("GET", "/user", token);
  await extensionContext?.secrets.store(GITHUB_PAT_SECRET_KEY, token);
  return { token, account: user.login, source: "pat" };
}

async function disconnectGitHubAccount(): Promise<void> {
  await extensionContext?.secrets.delete(GITHUB_PAT_SECRET_KEY);
  vscode.window.showInformationMessage(
    "Terrabot removed the manually stored GitHub token. VS Code GitHub sessions are managed through the Accounts menu.",
  );
}

// ── CLI subprocess helper (unchanged) ────────────────────────────────────────

function runTerrabot(args: string[], cwd: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(getCliPath(), args, { cwd, shell: false });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", chunk => { stdout += chunk.toString(); });
    child.stderr.on("data", chunk => { stderr += chunk.toString(); });
    child.on("error", err => reject(err));
    child.on("close", code => code === 0 ? resolve(stdout) : reject(new Error(stderr || `Terrabot exited with code ${code}`)));
  });
}

function runCommandOnce(command: string, args: string[], cwd: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      shell: false,
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", chunk => { stdout += chunk.toString(); });
    child.stderr.on("data", chunk => { stderr += chunk.toString(); });
    child.on("error", reject);
    child.on("close", code => {
      if (code === 0) {
        resolve(stdout.trim());
        return;
      }
      const detail = stderr.trim() || stdout.trim() || `exited with code ${code}`;
      reject(new Error(`${command} ${args.join(" ")}: ${detail}`));
    });
  });
}

async function runGitAuthenticated(args: string[], cwd: string, token: string): Promise<string> {
  const authenticatedArgs = [...args];
  const originIndex = authenticatedArgs.indexOf("origin");
  if (authenticatedArgs[0] === "push" && originIndex >= 0) {
    const remote = await runCommandOnce("git", ["remote", "get-url", "origin"], cwd);
    const { owner, repo } = parseGitHubRemote(remote);
    authenticatedArgs[originIndex] = `https://github.com/${owner}/${repo}.git`;
  }

  const storageRoot = extensionContext?.storageUri?.fsPath || extensionContext?.globalStorageUri.fsPath;
  if (!storageRoot) {
    throw new Error("Terrabot extension storage is unavailable for secure Git authentication.");
  }
  await fs.mkdir(storageRoot, { recursive: true });
  const isWindows = process.platform === "win32";
  const askPassPath = path.join(storageRoot, isWindows ? "github-askpass.cmd" : "github-askpass.sh");
  const askPass = isWindows
    ? "@echo off\r\nset prompt=%~1\r\necho %prompt% | findstr /I username >nul && (echo x-access-token) || (echo %TERRABOT_GITHUB_ASKPASS_TOKEN%)\r\n"
    : "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' 'x-access-token' ;; *) printf '%s\\n' \"$TERRABOT_GITHUB_ASKPASS_TOKEN\" ;; esac\n";
  await fs.writeFile(askPassPath, askPass, { mode: 0o700 });

  return new Promise((resolve, reject) => {
    const child = spawn("git", authenticatedArgs, {
      cwd,
      shell: false,
      env: {
        ...process.env,
        GIT_TERMINAL_PROMPT: "0",
        GIT_ASKPASS: askPassPath,
        SSH_ASKPASS: askPassPath,
        TERRABOT_GITHUB_ASKPASS_TOKEN: token,
      },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", chunk => { stdout += chunk.toString(); });
    child.stderr.on("data", chunk => { stderr += chunk.toString(); });
    child.on("error", reject);
    child.on("close", code => {
      if (code === 0) { resolve(stdout.trim()); return; }
      reject(new Error(`git ${authenticatedArgs.join(" ")}: ${stderr.trim() || stdout.trim() || `exited with code ${code}`}`));
    });
  });
}

function isGitIndexWriteError(message: string): boolean {
  return /could not write index|index\.lock|unable to create .*index\.lock|another git process|unable to write new index file/i.test(message || "");
}

function isGitIndexMutatingCommand(args: string[]): boolean {
  const mutating = new Set([
    "add", "checkout", "switch", "reset", "restore", "stash", "commit",
    "merge", "rebase", "cherry-pick", "revert", "rm", "mv", "read-tree",
    "update-index", "apply",
  ]);
  return args.some(arg => mutating.has(arg));
}

async function gitIndexLockPath(root: string): Promise<string> {
  const raw = await runCommandOnce("git", ["rev-parse", "--git-path", "index.lock"], root);
  return path.isAbsolute(raw) ? raw : path.join(root, raw);
}

async function removeStaleGitIndexLock(root: string, minimumAgeMs: number = 1500): Promise<boolean> {
  try {
    const lockPath = await gitIndexLockPath(root);
    const stat = await fs.stat(lockPath);
    if (Date.now() - stat.mtimeMs < minimumAgeMs) { return false; }
    await fs.unlink(lockPath);
    return true;
  } catch {
    return false;
  }
}

async function waitForGitIndexToSettle(root: string, timeoutMs: number = 12000): Promise<void> {
  await vscode.workspace.saveAll(false);
  const started = Date.now();
  let stableChecks = 0;

  while (Date.now() - started < timeoutMs) {
    try {
      const lockPath = await gitIndexLockPath(root);
      await fs.stat(lockPath);
      stableChecks = 0;
      await removeStaleGitIndexLock(root, 3000);
    } catch {
      stableChecks++;
      if (stableChecks >= 3) { return; }
    }
    await new Promise<void>(resolve => setTimeout(resolve, 250));
  }

  // Do not fail merely because VS Code SCM was slow. The command retry loop
  // below performs the authoritative check and stale-lock recovery.
}

async function unresolvedGitFiles(root: string): Promise<string> {
  try {
    return await runCommandOnce("git", ["diff", "--name-only", "--diff-filter=U"], root);
  } catch {
    return "";
  }
}

let gitCommandQueue: Promise<void> = Promise.resolve();

async function runGitCommandSerialized(args: string[], cwd: string): Promise<string> {
  const previous = gitCommandQueue;
  let release!: () => void;
  gitCommandQueue = new Promise<void>(resolve => { release = resolve; });
  await previous;

  try {
    if (isGitIndexMutatingCommand(args)) {
      await waitForGitIndexToSettle(cwd);
    }

    const maxAttempts = 12;
    let lastError: unknown;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await runCommandOnce("git", args, cwd);
      } catch (err) {
        lastError = err;
        const message = err instanceof Error ? err.message : String(err);
        if (!isGitIndexWriteError(message)) { throw err; }

        const unresolved = await unresolvedGitFiles(cwd);
        if (unresolved.trim()) {
          throw new Error(
            `Git cannot update the repository index because unresolved merge conflicts remain:
${unresolved}
Resolve them, save the files, and retry.`
          );
        }

        await removeStaleGitIndexLock(cwd, attempt >= 4 ? 750 : 3000);
        await new Promise<void>(resolve => setTimeout(resolve, Math.min(250 * attempt, 1500)));
      }
    }

    throw lastError instanceof Error
      ? lastError
      : new Error(`git ${args.join(" ")} failed after index recovery attempts.`);
  } finally {
    release();
  }
}

async function runCommand(command: string, args: string[], cwd: string): Promise<string> {
  if (command === "git") {
    return runGitCommandSerialized(args, cwd);
  }
  return runCommandOnce(command, args, cwd);
}

function isPullRequestPrompt(prompt: string): boolean {
  return /\b(raise|create|open|add|put|push)\b.*\b(pr|pull request)\b/i.test(prompt)
    || /\b(pr|pull request)\b.*\b(for these changes|for the changes|for the latest changes|now|separate|seperate|another|same|existing|current)\b/i.test(prompt);
}

function isPurePullRequestPrompt(prompt: string): boolean {
  if (!isPullRequestPrompt(prompt)) { return false; }
  const withoutPrRequest = prompt
    .replace(/\b(raise|create|open)\s+(?:a\s+)?(?:draft\s+)?(?:pr|pull request)\b/ig, " ")
    .replace(/\b(?:and|then)\s*(?:raise|create|open)\s+(?:a\s+)?(?:draft\s+)?(?:pr|pull request)\b/ig, " ")
    .replace(/\b(?:pr|pull request)\s+(?:for these changes|for the changes|now)\b/ig, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!withoutPrRequest) { return true; }

  const infraAction = /\b(add|create|provision|deploy|update|modify|change|set|enable|disable|remove|delete|decommission|refactor|fix|replace)\b/i;
  const infraSubject = /\b(terraform|infrastructure|module|resource|cloudamqp|rabbitmq|aws|azure|vpc|subnet|storage account|function app|vm|database|rds|s3|eks|vnet)\b/i;
  return !(infraAction.test(withoutPrRequest) || infraSubject.test(withoutPrRequest));
}

function isBranchPrompt(prompt: string): boolean {
  return /\b(create|make|open|switch)\b.*\b(github\s+)?branch\b/i.test(prompt);
}

function isPureBranchPrompt(prompt: string): boolean {
  if (!isBranchPrompt(prompt) || isPullRequestPrompt(prompt)) { return false; }

  const withoutBranchRequest = prompt
    .replace(/\b(?:create|make|open|switch)\s+(?:a\s+)?(?:new\s+)?(?:github\s+)?branch(?:\s+(?:named|called|as))?\s*[`'"]?[A-Za-z0-9._/-]*[`'"]?/ig, " ")
    .replace(/\b(?:and|then)\s*(?:push|publish)\s+(?:these|the|my)?\s*changes?\b/ig, " ")
    .replace(/\b(?:push|publish)\s+(?:these|the|my)?\s*changes?\b/ig, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!withoutBranchRequest) { return true; }

  const infraAction = /\b(add|create|provision|deploy|update|modify|change|set|enable|disable|remove|delete|decommission|refactor|fix|replace)\b/i;
  const infraSubject = /\b(terraform|infrastructure|infra|module|resource|cloud\s*amqp|cloudamqp|rabbit\s*mq|rabbitmq|aws|azure|vpc|subnet|storage account|function app|vm|database|rds|s3|eks|vnet|tfvars)\b/i;
  return !(infraAction.test(withoutBranchRequest) || infraSubject.test(withoutBranchRequest));
}


function isSamePullRequestPrompt(prompt: string): boolean {
  return /\b(same|existing|current)\s+(?:draft\s+)?(?:pr|pull request)\b/i.test(prompt)
    || /\badd\b.*\b(?:these|the|latest|new)\s+changes\b.*\b(?:same|existing|current)\s+(?:pr|pull request)\b/i.test(prompt);
}

function isSeparatePullRequestPrompt(prompt: string): boolean {
  return /\b(separate|seperate|another|new|different)\s+(?:draft\s+)?(?:pr|pull request)\b/i.test(prompt)
    || /\b(?:pr|pull request)\b.*\b(separate|seperate|another|new|different)\b/i.test(prompt);
}

const INVALID_BRANCH_NAME_WORDS = new Set([
  "a", "an", "and", "as", "branch", "create", "for", "from", "github",
  "make", "new", "open", "pr", "pull", "request", "separate", "seperate",
  "then", "the", "to", "use", "with",
]);

function sanitizeBranchPart(value: string): string {
  return value
    .trim()
    .replace(/^refs\/heads\//i, "")
    .replace(/[^A-Za-z0-9._/-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/\/{2,}/g, "/")
    .replace(/^[-/.]+|[-/.]+$/g, "")
    .slice(0, 100);
}

function requestedBranchName(prompt: string): string {
  const patterns = [
    /\bbranch\s+(?:named|called|as)\s+[`'"]?([A-Za-z0-9._/-]+)[`'"]?/i,
    /\b(?:create|make|open)\s+(?:a\s+)?(?:new\s+)?(?:github\s+)?branch\s+[`'"]?([A-Za-z0-9._/-]+)[`'"]?/i,
  ];

  for (const pattern of patterns) {
    const match = prompt.match(pattern);
    const candidate = sanitizeBranchPart(match?.[1] || "");
    if (!candidate) { continue; }
    if (INVALID_BRANCH_NAME_WORDS.has(candidate.toLowerCase())) { continue; }
    return candidate;
  }
  return "";
}

function changeSlugFromPrompt(prompt: string): string {
  const cleaned = prompt
    .toLowerCase()
    .replace(/\b(?:create|make|open)\s+(?:a\s+)?(?:new\s+)?(?:github\s+)?branch(?:\s+(?:named|called|as))?\s*[a-z0-9._/-]*/ig, " ")
    .replace(/\b(?:raise|create|open)\s+(?:a\s+)?(?:draft\s+)?(?:pr|pull request)\b/ig, " ")
    .replace(/\b(?:and|then|separate|seperate|for|the|changes?|please|infra(?:structure)?)\b/ig, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

  const words = cleaned.split(/\s+/).filter(Boolean);
  const important = words.filter(word => !new Set([
    "add", "apply", "change", "create", "delete", "enable", "modify", "new",
    "remove", "set", "update", "use",
  ]).has(word));

  const ordered = [...important];
  for (const action of ["disable", "enable", "remove", "delete", "update", "create"]) {
    if (words.includes(action) && !ordered.includes(action)) { ordered.push(action); }
  }

  return sanitizeBranchPart(ordered.slice(0, 4).join("-")) || "terrabot-change";
}

async function resolveWorkspaceUser(root: string): Promise<string> {
  try {
    const session = await vscode.authentication.getSession("github", ["read:user"], { createIfNone: false });
    const account = sanitizeBranchPart(session?.account?.label || "");
    if (account) { return account.split("@")[0]; }
  } catch { /* fall through to Git identity */ }

  for (const args of [["config", "user.email"], ["config", "user.name"]]) {
    try {
      const value = await runCommand("git", args, root);
      const candidate = sanitizeBranchPart(value.includes("@") ? value.split("@")[0] : value.replace(/\s+/g, "-"));
      if (candidate) { return candidate; }
    } catch { /* try the next identity source */ }
  }

  return sanitizeBranchPart(process.env.USER || process.env.USERNAME || "terrabot") || "terrabot";
}

async function defaultBranchName(root: string, prompt: string): Promise<string> {
  return `${await resolveWorkspaceUser(root)}/${changeSlugFromPrompt(prompt)}`;
}

function parseGitHubRemote(remoteUrl: string): { owner: string; repo: string } {
  const trimmed = remoteUrl.trim().replace(/\.git$/, "");
  let match = trimmed.match(/^git@github\.com:([^/]+)\/(.+)$/);
  if (!match) { match = trimmed.match(/^https:\/\/github\.com\/([^/]+)\/(.+)$/); }
  if (!match) { throw new Error(`Unsupported GitHub origin URL: ${remoteUrl}`); }
  return { owner: match[1], repo: match[2] };
}

function githubJson<T>(method: string, apiPath: string, token: string, body?: unknown): Promise<T> {
  const payload = body === undefined ? "" : JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const req = https.request({
      method,
      hostname: "api.github.com",
      path: apiPath,
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${token}`,
        "User-Agent": "terrabot-vscode",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(payload ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) } : {})
      }
    }, res => {
      let data = "";
      res.on("data", chunk => { data += chunk.toString(); });
      res.on("end", () => {
        let parsed: any = {};
        try { parsed = data ? JSON.parse(data) : {}; } catch { parsed = { message: data }; }
        const status = res.statusCode || 500;
        if (status >= 400) {
          reject(new Error(parsed.message || `GitHub API failed with HTTP ${status}`));
          return;
        }
        resolve(parsed as T);
      });
    });
    req.on("error", reject);
    if (payload) { req.write(payload); }
    req.end();
  });
}

async function resolveGitContext(root: string): Promise<{ owner: string; repo: string; base: string; branch: string; commit: string }> {
  const remote = await runCommand("git", ["remote", "get-url", "origin"], root);
  const { owner, repo } = parseGitHubRemote(remote);
  // Terrabot PR workflows intentionally use the remote main branch as the
  // single source of truth. A stale/diverged local main branch is never used
  // as the base for feature branches or rebases.
  const base = GITHUB_BASE_BRANCH;
  const branch = await runCommand("git", ["branch", "--show-current"], root);
  const commit = await runCommand("git", ["rev-parse", "HEAD"], root);
  return { owner, repo, base, branch, commit };
}


async function gitPathExists(root: string, gitPathName: string): Promise<boolean> {
  try {
    const raw = await runCommandOnce("git", ["rev-parse", "--git-path", gitPathName], root);
    const resolved = path.isAbsolute(raw) ? raw : path.join(root, raw);
    await fs.stat(resolved);
    return true;
  } catch {
    return false;
  }
}

async function isRebaseInProgress(root: string): Promise<boolean> {
  return (await gitPathExists(root, "rebase-merge")) || (await gitPathExists(root, "rebase-apply"));
}

type WorkspaceSnapshotEntry = {
  path: string;
  deleted: boolean;
  contentBase64?: string;
};

type WorkspaceSnapshot = {
  entries: WorkspaceSnapshotEntry[];
};

async function captureWorkspaceSnapshot(root: string): Promise<WorkspaceSnapshot> {
  await vscode.workspace.saveAll(false);

  const tracked = await runCommandOnce("git", ["diff", "HEAD", "--name-only", "-z"], root);
  const untracked = await runCommandOnce("git", ["ls-files", "--others", "--exclude-standard", "-z"], root);
  const paths = new Set<string>();
  for (const value of `${tracked}\0${untracked}`.split("\0")) {
    const relativePath = value.trim();
    if (relativePath) { paths.add(relativePath); }
  }

  const entries: WorkspaceSnapshotEntry[] = [];
  for (const relativePath of paths) {
    const absolutePath = path.join(root, relativePath);
    try {
      const content = await fs.readFile(absolutePath);
      entries.push({ path: relativePath, deleted: false, contentBase64: content.toString("base64") });
    } catch {
      entries.push({ path: relativePath, deleted: true });
    }
  }
  return { entries };
}

async function restoreWorkspaceSnapshot(root: string, snapshot: WorkspaceSnapshot): Promise<void> {
  for (const entry of snapshot.entries) {
    const absolutePath = path.join(root, entry.path);
    if (entry.deleted) {
      try { await fs.unlink(absolutePath); } catch { /* already absent */ }
      continue;
    }
    await fs.mkdir(path.dirname(absolutePath), { recursive: true });
    await fs.writeFile(absolutePath, Buffer.from(entry.contentBase64 || "", "base64"));
  }
  await vscode.workspace.saveAll(false);
}

async function abortInterruptedGitOperation(root: string, notes: string[], reporter?: GitProgressReporter): Promise<void> {
  if (await isRebaseInProgress(root)) {
    await runCommand("git", ["rebase", "--abort"], root);
    reportGitStep(notes, reporter, "Aborted the interrupted rebase to prevent the merge-resolution loop.");
  }
  if (await gitPathExists(root, "MERGE_HEAD")) {
    await runCommand("git", ["merge", "--abort"], root);
    reportGitStep(notes, reporter, "Aborted the interrupted merge to return the repository to a stable state.");
  }
}

async function uniqueFreshBranchName(root: string, requested: string): Promise<string> {
  let candidate = requested;
  let suffix = 2;
  while (true) {
    const local = await runCommand("git", ["branch", "--list", candidate], root);
    let remoteExists = false;
    try {
      const remote = await runCommand("git", ["ls-remote", "--heads", "origin", candidate], root);
      remoteExists = Boolean(remote.trim());
    } catch { /* remote lookup is advisory */ }
    if (!local.trim() && !remoteExists) { return candidate; }
    candidate = `${requested}-${suffix++}`;
  }
}

async function createBranchFromWorkspace(root: string, prompt: string, reporter?: GitProgressReporter): Promise<{ branchUrl: string; compareUrl: string; branch: string; notes: string[] }> {
  const initialContext = await resolveGitContext(root);
  let requested = requestedBranchName(prompt);
  if (!requested) { requested = await defaultBranchName(root, prompt); }
  if (requested === initialContext.base || requested === "main" || requested === "master") {
    throw new Error("Choose a new branch name that is different from the base branch.");
  }

  const notes: string[] = [];
  await abortInterruptedGitOperation(root, notes, reporter);
  const snapshot = await captureWorkspaceSnapshot(root);
  reportGitStep(notes, reporter, `Captured ${snapshot.entries.length} pending workspace change(s) before switching branches.`);

  // Clear only after the snapshot is safely in memory. This avoids stash-pop
  // conflicts entirely and therefore avoids Merge Editor/polling loops.
  await runCommand("git", ["reset", "--hard", "HEAD"], root);
  await runCommand("git", ["clean", "-fd"], root);
  await runCommand("git", ["fetch", "origin", GITHUB_BASE_BRANCH], root);
  reportGitStep(notes, reporter, "Fetched the latest origin/main as the authoritative base.");

  const branch = await uniqueFreshBranchName(root, requested);
  if (branch !== requested) {
    reportGitStep(notes, reporter, `Branch ${requested} already existed, so Terrabot selected ${branch} to avoid overwriting it.`);
  }
  await runCommand("git", ["checkout", "-b", branch, `origin/${GITHUB_BASE_BRANCH}`], root);
  reportGitStep(notes, reporter, `Created ${branch} directly from the latest origin/${GITHUB_BASE_BRANCH}.`);

  await restoreWorkspaceSnapshot(root, snapshot);
  reportGitStep(notes, reporter, "Reapplied the pending workspace changes onto the fresh branch without using stash, merge, or rebase conflict resolution.");

  return {
    branchUrl: `https://github.com/${initialContext.owner}/${initialContext.repo}/tree/${branch}`,
    compareUrl: `https://github.com/${initialContext.owner}/${initialContext.repo}/compare/${GITHUB_BASE_BRANCH}...${branch}`,
    branch,
    notes,
  };
}

async function ensureWorkspaceChangeBranch(
  root: string,
  prompt: string = "",
  forceSeparate: boolean = false,
  reporter?: GitProgressReporter,
): Promise<string[]> {
  const context = await resolveGitContext(root);
  const explicitBranch = requestedBranchName(prompt);
  const defaultSuggestion = explicitBranch || await defaultBranchName(root, prompt);
  const suggestedBranch = forceSeparate && defaultSuggestion === currentWorkspacePrBranch
    ? `${defaultSuggestion}-2`
    : defaultSuggestion;

  // Modal messages already include VS Code's built-in Cancel action. Do not
  // add another explicit Cancel button, otherwise the branch prompt shows two.
  const choices = forceSeparate
    ? ["Yes - Create New Branch"]
    : ["Yes - Create New Branch", "No - Use Current Branch"];

  const action = await vscode.window.showWarningMessage(
    forceSeparate
      ? `A separate pull request requires a separate source branch. Create one after updating from origin/${context.base}?`
      : `Before pushing, do you want Terrabot to create and switch to a new branch after updating from origin/${context.base}?`,
    { modal: true },
    ...choices,
  );

  if (action === "No - Use Current Branch" && !forceSeparate) {
    // Explicitly remain on the current branch. Do not fetch, checkout, or
    // mutate branch state when the user answers no.
    return ["Kept the current branch as requested."];
  }
  if (action !== "Yes - Create New Branch") {
    throw new Error("Push and pull request creation were cancelled.");
  }

  const branchName = await vscode.window.showInputBox({
    title: "Terrabot Branch Name",
    prompt: `Enter a branch name. It will be created after pulling the latest origin/${context.base}.`,
    value: suggestedBranch,
    validateInput: value => {
      const cleaned = sanitizeBranchPart(value);
      if (!cleaned || cleaned !== value) {
        return "Use only letters, numbers, '.', '_', '/', and '-'.";
      }
      if (INVALID_BRANCH_NAME_WORDS.has(cleaned.toLowerCase())) {
        return "Enter a descriptive branch name, not a connector word.";
      }
      if (cleaned === context.base || cleaned === "main" || cleaned === "master") {
        return "Use a branch name different from the base branch.";
      }
      if (forceSeparate && cleaned === currentWorkspacePrBranch) {
        return "A separate PR must use a branch different from the existing PR branch.";
      }
      return undefined;
    },
  });
  if (!branchName) {
    throw new Error("Push and pull request creation were cancelled because no branch name was provided.");
  }

  const created = await createBranchFromWorkspace(root, `create branch ${branchName}`, reporter);
  vscode.window.showInformationMessage(`Terrabot switched to GitHub branch ${created.branch}.`);
  return created.notes;
}

async function preserveWorkspaceChanges(root: string, notes: string[], reporter?: GitProgressReporter): Promise<void> {
  await vscode.workspace.saveAll(false);
  const status = await runCommand("git", ["status", "--porcelain"], root);
  if (!status.trim()) { return; }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  await runCommand("git", ["stash", "push", "-u", "-m", `terrabot-preserved-before-new-branch-${stamp}`], root);
  reportGitStep(
    notes,
    reporter,
    "Preserved pre-existing local/workspace changes in a Git stash so they are not included in the new Terrabot branch.",
  );
}

async function createFreshBranchBeforeGeneration(
  root: string,
  prompt: string,
  requestedName: string,
  reporter?: GitProgressReporter,
): Promise<PreparedGitTarget> {
  const notes: string[] = [];
  await abortInterruptedGitOperation(root, notes, reporter);
  await preserveWorkspaceChanges(root, notes, reporter);

  await runCommand("git", ["fetch", "origin", GITHUB_BASE_BRANCH], root);
  reportGitStep(notes, reporter, `Fetched the latest origin/${GITHUB_BASE_BRANCH} before creating the branch.`);

  const requested = sanitizeBranchPart(requestedName) || await defaultBranchName(root, prompt);
  if (requested === GITHUB_BASE_BRANCH || requested === "main" || requested === "master") {
    throw new Error("Choose a new branch name that is different from the base branch.");
  }

  const branch = await uniqueFreshBranchName(root, requested);
  if (branch !== requested) {
    reportGitStep(notes, reporter, `Branch ${requested} already existed, so Terrabot selected ${branch}.`);
  }

  await runCommand("git", ["checkout", "-b", branch, `origin/${GITHUB_BASE_BRANCH}`], root);
  reportGitStep(
    notes,
    reporter,
    `Created ${branch} from the latest origin/${GITHUB_BASE_BRANCH} before generating infrastructure changes.`,
  );

  return { branch, notes, mode: "new", prTarget: "new" };
}

async function prepareGitTargetBeforeGeneration(
  root: string,
  prompt: string,
  wantsPullRequest: boolean,
  wantsBranch: boolean,
  reporter?: GitProgressReporter,
): Promise<PreparedGitTarget | undefined> {
  if (!wantsPullRequest && !wantsBranch) { return undefined; }

  if (wantsPullRequest && currentWorkspacePrBranch && currentWorkspacePrUrl) {
    const target = await choosePullRequestTarget(prompt, false);
    if (target === "existing") {
      const notes: string[] = [];
      const current = await resolveGitContext(root);
      if (current.branch !== currentWorkspacePrBranch) {
        await preserveWorkspaceChanges(root, notes, reporter);
        await runCommand("git", ["fetch", "origin", currentWorkspacePrBranch], root);
        await runCommand("git", ["checkout", currentWorkspacePrBranch], root);
        await runCommand("git", ["reset", "--hard", `origin/${currentWorkspacePrBranch}`], root);
        reportGitStep(notes, reporter, `Switched to existing PR branch ${currentWorkspacePrBranch} before applying the latest request.`);
      }
      return {
        branch: currentWorkspacePrBranch,
        notes,
        mode: "existing-pr",
        prTarget: "existing",
      };
    }

    const suggested = requestedBranchName(prompt) || await defaultBranchName(root, prompt);
    const branchName = await vscode.window.showInputBox({
      title: "Terrabot Branch Name",
      prompt: `Enter a new branch name. It will be created from the latest origin/${GITHUB_BASE_BRANCH} before generation.`,
      value: suggested === currentWorkspacePrBranch ? `${suggested}-2` : suggested,
      validateInput: value => {
        const cleaned = sanitizeBranchPart(value);
        if (!cleaned || cleaned !== value) { return "Use only letters, numbers, '.', '_', '/', and '-'."; }
        if (cleaned === currentWorkspacePrBranch) { return "A new PR requires a different branch."; }
        if (cleaned === GITHUB_BASE_BRANCH || cleaned === "main" || cleaned === "master") { return "Use a feature branch name."; }
        return undefined;
      },
    });
    if (!branchName) { throw new Error("New pull request creation was cancelled."); }
    return createFreshBranchBeforeGeneration(root, prompt, branchName, reporter);
  }

  const context = await resolveGitContext(root);
  const action = await vscode.window.showWarningMessage(
    `Before applying the infrastructure change, do you want Terrabot to create a clean branch from the latest origin/${GITHUB_BASE_BRANCH}?`,
    { modal: true },
    "Yes - Create New Branch",
    "No - Use Current Branch",
  );

  if (action === "No - Use Current Branch") {
    return {
      branch: context.branch,
      notes: ["Kept the current branch; existing local changes remain part of this branch workflow."],
      mode: "current",
      prTarget: "normal",
    };
  }
  if (action !== "Yes - Create New Branch") {
    throw new Error("Branch selection was cancelled.");
  }

  const suggested = requestedBranchName(prompt) || await defaultBranchName(root, prompt);
  const branchName = await vscode.window.showInputBox({
    title: "Terrabot Branch Name",
    prompt: `Enter a branch name. It will be created from the latest origin/${GITHUB_BASE_BRANCH} before generation.`,
    value: suggested,
    validateInput: value => {
      const cleaned = sanitizeBranchPart(value);
      if (!cleaned || cleaned !== value) { return "Use only letters, numbers, '.', '_', '/', and '-'."; }
      if (INVALID_BRANCH_NAME_WORDS.has(cleaned.toLowerCase())) { return "Enter a descriptive branch name."; }
      if (cleaned === GITHUB_BASE_BRANCH || cleaned === "main" || cleaned === "master") { return "Use a feature branch name."; }
      return undefined;
    },
  });
  if (!branchName) { throw new Error("Branch creation was cancelled because no branch name was provided."); }
  return createFreshBranchBeforeGeneration(root, prompt, branchName, reporter);
}

async function readPullRequestTemplate(root: string): Promise<string> {
  const fixedCandidates = [
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/pull_request_template.md",
    "PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md",
    "docs/PULL_REQUEST_TEMPLATE.md",
    "docs/pull_request_template.md",
  ];

  for (const candidate of fixedCandidates) {
    try {
      const bytes = await vscode.workspace.fs.readFile(vscode.Uri.file(path.join(root, candidate)));
      const content = Buffer.from(bytes).toString("utf8").trim();
      if (content) { return content; }
    } catch { /* try the next standard template location */ }
  }

  const templateFolder = vscode.Uri.file(path.join(root, ".github", "PULL_REQUEST_TEMPLATE"));
  try {
    const entries = await vscode.workspace.fs.readDirectory(templateFolder);
    const markdownTemplates = entries
      .filter(([name, type]) => type === vscode.FileType.File && name.toLowerCase().endsWith(".md"))
      .sort(([left], [right]) => left.localeCompare(right));
    if (markdownTemplates.length) {
      const bytes = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(templateFolder, markdownTemplates[0][0]));
      return Buffer.from(bytes).toString("utf8").trim();
    }
  } catch { /* backend will try the GitHub repository template */ }

  return "";
}

async function choosePullRequestTarget(prompt: string, forceSeparate: boolean): Promise<"existing" | "new" | "normal"> {
  if (forceSeparate || isSeparatePullRequestPrompt(prompt)) { return "new"; }
  if (isSamePullRequestPrompt(prompt) && currentWorkspacePrBranch) { return "existing"; }
  if (!currentWorkspacePrBranch || !currentWorkspacePrUrl) { return "normal"; }
  const action = await vscode.window.showInformationMessage(
    `This chat already has a pull request on branch ${currentWorkspacePrBranch}. Where should the latest changes go?`,
    { modal: true },
    "Push Commit to Existing PR",
    "Create New PR",
    "Cancel",
  );
  if (action === "Push Commit to Existing PR") { return "existing"; }
  if (action === "Create New PR") { return "new"; }
  throw new Error("Pull request creation was cancelled.");
}

async function pushBranchWithRecovery(
  root: string,
  branch: string,
  notes: string[],
  reporter?: GitProgressReporter,
  githubToken?: string,
): Promise<void> {
  try {
    if (githubToken) {
      await runGitAuthenticated(["push", "-u", "origin", branch], root, githubToken);
    } else {
      await runCommand("git", ["push", "-u", "origin", branch], root);
    }
    reportGitStep(notes, reporter, `Pushed branch ${branch} to origin.`);
    return;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (/authentication failed|permission denied|403|401|repository not found|write access/i.test(message)) {
      throw err;
    }
    if (!/non-fast-forward|fetch first|rejected|remote contains work/i.test(message)) {
      throw err;
    }

    reportGitStep(notes, reporter, `Push was rejected because the remote branch changed. Fetching origin/${branch} and retrying safely.`);
    try {
      await runCommand("git", ["fetch", "origin", branch], root);
    } catch { /* the branch may not exist remotely yet */ }

    // The branch has already been rebased onto origin/main. A force-with-lease
    // updates only the expected remote ref and refuses to overwrite a branch
    // that changed again after the fetch.
    if (githubToken) {
      await runGitAuthenticated(["push", "--force-with-lease", "-u", "origin", branch], root, githubToken);
    } else {
      await runCommand("git", ["push", "--force-with-lease", "-u", "origin", branch], root);
    }
    reportGitStep(notes, reporter, `Recovered the rejected push with --force-with-lease and updated origin/${branch}.`);
  }
}

async function pushWorkspaceChangesToBranch(
  root: string,
  prompt: string,
  reporter?: GitProgressReporter,
  preparedTarget?: PreparedGitTarget,
): Promise<{ branchUrl: string; compareUrl: string; branch: string; notes: string[] }> {
  const notes: string[] = [...(preparedTarget?.notes || [])];
  if (!preparedTarget) {
    const branchNotes = await ensureWorkspaceChangeBranch(root, prompt, false, reporter);
    notes.push(...branchNotes);
  }

  const context = await resolveGitContext(root);
  if (!context.branch || context.branch === GITHUB_BASE_BRANCH) {
    throw new Error("Terrabot requires a feature branch before pushing infrastructure changes.");
  }

  const status = await runCommand("git", ["status", "--porcelain"], root);
  if (status) {
    const commitTitle = changeSlugFromPrompt(prompt).replace(/-/g, " ") || "Apply Terrabot infrastructure changes";
    await runCommand("git", ["add", "-A"], root);
    try {
      await runCommand("git", ["commit", "-m", commitTitle], root);
      reportGitStep(notes, reporter, `Committed generated infrastructure changes on ${context.branch}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (!/nothing to commit|no changes added/i.test(message)) { throw err; }
    }
  }

  const githubAuth = await connectGitHubAccount();
  reportGitStep(notes, reporter, `Using GitHub account ${githubAuth.account} for branch push.`);
  await pushBranchWithRecovery(root, context.branch, notes, reporter, githubAuth.token);
  return {
    branchUrl: `https://github.com/${context.owner}/${context.repo}/tree/${context.branch}`,
    compareUrl: `https://github.com/${context.owner}/${context.repo}/compare/${context.base}...${context.branch}`,
    branch: context.branch,
    notes,
  };
}

async function createPullRequestFromWorkspace(
  root: string,
  prompt: string,
  forceSeparate: boolean = false,
  reporter?: GitProgressReporter,
  preparedTarget?: PreparedGitTarget,
): Promise<{ prUrl: string; compareUrl: string; branch: string; notes: string[]; existing: boolean }> {
  const notes: string[] = [...(preparedTarget?.notes || [])];
  await abortInterruptedGitOperation(root, notes, reporter);

  const target = preparedTarget?.prTarget || await choosePullRequestTarget(prompt, forceSeparate);
  if (!preparedTarget && target === "existing") {
    const snapshot = await captureWorkspaceSnapshot(root);
    await runCommand("git", ["reset", "--hard", "HEAD"], root);
    await runCommand("git", ["clean", "-fd"], root);
    await runCommand("git", ["fetch", "origin", currentWorkspacePrBranch], root);
    await runCommand("git", ["checkout", currentWorkspacePrBranch], root);
    try {
      await runCommand("git", ["reset", "--hard", `origin/${currentWorkspacePrBranch}`], root);
      reportGitStep(notes, reporter, `Updated the existing PR branch from origin/${currentWorkspacePrBranch}.`);
    } catch {
      reportGitStep(notes, reporter, `Using the local existing PR branch ${currentWorkspacePrBranch}.`);
    }
    await restoreWorkspaceSnapshot(root, snapshot);
    reportGitStep(notes, reporter, "Reapplied the latest workspace changes to the existing PR branch without rebasing.");
  } else if (!preparedTarget) {
    const branchNotes = await ensureWorkspaceChangeBranch(root, prompt, target === "new", reporter);
    notes.push(...branchNotes);
  }

  const context = await resolveGitContext(root);
  const branch = context.branch;
  if (!branch || branch === GITHUB_BASE_BRANCH) {
    throw new Error("Terrabot requires a feature branch before creating a pull request.");
  }

  const status = await runCommand("git", ["status", "--porcelain"], root);
  const fallbackCommitTitle = prompt.replace(/^.*?(raise|create|open)\s+(a\s+)?(pr|pull request)\s*(for)?/i, "").trim() || "Apply Terrabot workspace changes";
  if (status) {
    await runCommand("git", ["add", "-A"], root);
    try { await runCommand("git", ["commit", "-m", fallbackCommitTitle], root); }
    catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (!/nothing to commit|no changes added/i.test(message)) { throw err; }
    }
  }

  const githubAuth = await connectGitHubAccount();
  reportGitStep(notes, reporter, `Using GitHub account ${githubAuth.account} for push and pull request operations.`);
  await pushBranchWithRecovery(root, branch, notes, reporter, githubAuth.token);
  reportGitStep(notes, reporter, `Pushed ${branch}; no Merge Editor or rebase conflict loop was used.`);

  const template = await readPullRequestTemplate(root);
  await runCommand("git", ["fetch", "origin", GITHUB_BASE_BRANCH], root);
  const compareRef = `origin/${GITHUB_BASE_BRANCH}...HEAD`;
  const changedFiles = await runCommand("git", ["diff", "--name-status", compareRef], root);
  const diffStat = await runCommand("git", ["diff", "--stat", compareRef], root);
  let diff = await runCommand("git", ["diff", "--no-color", "--unified=3", compareRef], root);
  if (diff.length > 60000) { diff = `${diff.slice(0, 60000)}\n\n[Diff truncated by Terrabot after 60000 characters.]`; }

  const metadata = await postJson(`${getBackendBaseUrl()}/api/vscode/github-pr-metadata`, {
    owner: context.owner, repo: context.repo, head: branch, base: GITHUB_BASE_BRANCH, template, prompt,
    changed_files: changedFiles, diff_stat: diffStat, diff,
  });
  const title = String(metadata.title || fallbackCommitTitle).slice(0, 240);
  const body = String(metadata.body || template || `## Description\n\n${prompt}`);
  const head = `${context.owner}:${branch}`;
  const existing = await githubJson<Array<{ number: number; html_url: string }>>(
    "GET",
    `/repos/${encodeURIComponent(context.owner)}/${encodeURIComponent(context.repo)}/pulls?state=open&head=${encodeURIComponent(head)}&base=${encodeURIComponent(GITHUB_BASE_BRANCH)}`,
    githubAuth.token,
  );

  let prUrl = "";
  let existed = false;
  if (existing.length) {
    const updated = await githubJson<{ html_url: string }>(
      "PATCH",
      `/repos/${encodeURIComponent(context.owner)}/${encodeURIComponent(context.repo)}/pulls/${existing[0].number}`,
      githubAuth.token,
      { title, body },
    );
    prUrl = updated.html_url;
    existed = true;
  } else {
    const created = await githubJson<{ html_url: string }>(
      "POST",
      `/repos/${encodeURIComponent(context.owner)}/${encodeURIComponent(context.repo)}/pulls`,
      githubAuth.token,
      { title, head: branch, base: GITHUB_BASE_BRANCH, body, draft: true },
    );
    prUrl = created.html_url;
  }

  currentWorkspacePrBranch = branch;
  currentWorkspacePrUrl = prUrl;
  return {
    prUrl: currentWorkspacePrUrl,
    compareUrl: `https://github.com/${context.owner}/${context.repo}/compare/${GITHUB_BASE_BRANCH}...${branch}`,
    branch, notes, existing: existed,
  };
}

// ── HTTP helper (unchanged) ───────────────────────────────────────────────────

async function postJson(url: string, payload: unknown): Promise<any> {
  const body = JSON.stringify(payload);
  const target = new URL(url);
  const client = target.protocol === "http:" ? http : https;
  const token = getApiToken();
  return new Promise((resolve, reject) => {
    const req = client.request({
      method: "POST",
      hostname: target.hostname,
      port: target.port,
      path: `${target.pathname}${target.search}`,
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
        ...(token ? { "Authorization": `Bearer ${token}` } : {})
      }
    }, res => {
      let data = "";
      res.on("data", chunk => { data += chunk.toString(); });
      res.on("end", () => {
        let parsed: any = data;
        try { parsed = JSON.parse(data); } catch { /* keep raw text */ }
        if ((res.statusCode || 500) >= 400) {
          reject(new Error(typeof parsed === "string" ? parsed : (parsed.error ? `${parsed.reply || "Request failed"} ${parsed.error}` : (parsed.reply || JSON.stringify(parsed)))));
          return;
        }
        resolve(parsed);
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

// ── repo context collector ───────────────────────────────────────────────────

function explicitIaCPathsFromPrompt(prompt: string): string[] {
  const found: string[] = [];
  const pattern = /(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*\.(?:tf|tfvars))(?![A-Za-z0-9_.-])/gi;
  for (const match of prompt.matchAll(pattern)) {
    const value = String(match[1] || "").replace(/\\/g, "/").replace(/^\/+/, "");
    if (value && !found.includes(value)) { found.push(value); }
  }
  return found;
}

function promptEnvironmentScore(filePath: string, prompt: string): number {
  const normalizedPrompt = prompt.toLowerCase().replace(/_/g, "-");
  return filePath
    .toLowerCase()
    .replace(/_/g, "-")
    .split("/")
    .filter(Boolean)
    .reduce((score, part) => {
      const escaped = part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return score + (new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`).test(normalizedPrompt) ? 20 + part.length : 0);
    }, 0);
}


function isAwsResourceCreationPrompt(prompt: string): boolean {
  const text = prompt.toLowerCase();
  const createIntent = /\b(create|add|provision|deploy|new|generate|build)\b/.test(text);
  const awsFamily = /\b(aws|redshift|rds|ec2|s3|eks|lambda|dynamodb|cloudfront|elasticache|iam|vpc)\b/.test(text);
  return createIntent && awsFamily;
}

function awsResourceFamilyTermsFromPrompt(prompt: string): string[] {
  const text = prompt.toLowerCase();
  const terms = new Set<string>();
  const add = (...values: string[]) => values.forEach(value => terms.add(value));

  if (/\bredshift\b/.test(text)) {
    add("redshift", "auditdb", "staging", "parameter_group", "subnet_group");
  }
  if (/\brds\b|\bmysql\b|\bpostgres(?:ql)?\b|\bmssql\b/.test(text)) {
    add("rds", "mysql_instance", "postgres_instance", "mssql_instance", "subnet_group");
  }
  if (/\bec2\b|instance/.test(text)) { add("ec2", "instance"); }
  if (/\bs3\b|bucket/.test(text)) { add("s3", "bucket"); }
  if (/\beks\b|kubernetes/.test(text)) { add("eks"); }
  if (/\blambda\b/.test(text)) { add("lambda", "lambdas"); }
  if (/\bdynamodb\b/.test(text)) { add("dynamodb"); }
  if (/\bcloudfront\b|\bcdn\b/.test(text)) { add("cloudfront", "cdn"); }
  if (/\belasticache\b|redis/.test(text)) { add("elasticache", "redis"); }
  if (/\biam\b/.test(text)) { add("iam"); }
  if (/\bvpc\b/.test(text)) { add("vpc", "vena_vpc"); }

  return [...terms];
}

function isAwsCloneOrMirrorPrompt(prompt: string): boolean {
  const text = prompt.toLowerCase();
  return isAwsResourceCreationPrompt(prompt)
    && /\b(mirror|mirroring|clone|copy|copying|based on|same as|replicate)\b/.test(text)
    && /\b(module|inputs?|consumer|auditdb)\b/.test(text);
}

function isAzureResourceCreationPrompt(prompt: string): boolean {
  const text = prompt.toLowerCase();
  const createIntent = /\b(create|add|provision|deploy|new)\b/.test(text);
  const azureFamily = /\b(azure|azurerm|aca|container\s*app|container[-_ ]apps?|storage\s*account|key\s*vault|application\s*gateway|app\s*service|function\s*app)\b/.test(text);
  return createIntent && azureFamily;
}

function resourceFamilyTermsFromPrompt(prompt: string): string[] {
  const text = prompt.toLowerCase();
  const terms = new Set<string>();

  const add = (...values: string[]) => values.forEach(value => terms.add(value));
  if (/\baca\b|container\s*app|container[-_ ]apps?/.test(text)) {
    add("aca", "container_app", "container-app", "container app", "container_apps", "azurerm_container_app", "tf-azure-container-apps");
  }
  if (/storage\s*account|storage_account/.test(text)) {
    add("storage_account", "storage-account", "storage account", "azurerm_storage_account");
  }
  if (/key\s*vault|key_vault/.test(text)) {
    add("key_vault", "key-vault", "key vault", "azurerm_key_vault");
  }
  if (/function\s*app|function_app/.test(text)) {
    add("function_app", "function-app", "function app", "azurerm_linux_function_app", "azurerm_windows_function_app");
  }
  if (/app\s*service|app_service/.test(text)) {
    add("app_service", "app-service", "app service", "azurerm_linux_web_app", "azurerm_windows_web_app");
  }
  if (/application\s*gateway|application_gateway/.test(text)) {
    add("application_gateway", "application-gateway", "application gateway", "azurerm_application_gateway");
  }

  return [...terms];
}

function resourceFamilyEvidenceScore(filePath: string, content: string, prompt: string): number {
  const terms = resourceFamilyTermsFromPrompt(prompt);
  if (!terms.length) { return 0; }
  const normalizedPath = filePath.toLowerCase().replace(/\\/g, "/");
  const normalizedContent = content.toLowerCase();
  let score = 0;
  for (const term of terms) {
    if (normalizedPath.includes(term.replace(/ /g, "_")) || normalizedPath.includes(term.replace(/ /g, "-"))) { score += 700; }
    if (normalizedContent.includes(term)) { score += 350; }
  }
  score += promptEnvironmentScore(filePath, prompt) * 10;
  return score;
}

function isTargetEnvironmentCompanionFile(filePath: string, prompt: string): boolean {
  if (promptEnvironmentScore(filePath, prompt) <= 0) { return false; }
  const base = filePath.replace(/\\/g, "/").split("/").pop()?.toLowerCase() || "";
  return base === "hub.tfvars" || base === "tier.tfvars" || base === "common.tfvars" || base === "variables.tf";
}

function routingSymbolsFromPrompt(prompt: string): string[] {
  const text = prompt.toLowerCase();
  const symbols = new Set<string>();

  // Preserve exact Terraform identifiers supplied by the user.
  for (const token of text.match(/[a-z][a-z0-9_]{3,}/g) || []) {
    if (token.includes("_")) { symbols.add(token); }
  }

  // Expand common natural-language requests into the exact repository-owned
  // Terraform assignments. These symbols are used only to locate evidence;
  // the backend/model still decides the requested value.
  const isCloudAmqp = /cloud\s*amqp|cloudamqp|rabbit\s*mq|rabbitmq/.test(text);
  if (isCloudAmqp) {
    symbols.add("create_cloudamqp");
    if (/datadog/.test(text) && /log|logs|logging/.test(text)) {
      symbols.add("cloudamqp_enable_datadog_logs");
    }
    if (/datadog/.test(text) && /metric|metrics|monitoring/.test(text)) {
      symbols.add("cloudamqp_enable_datadog_metrics");
    }
  }
  if (/patch\s*management/.test(text)) { symbols.add("create_patch_management"); }
  if (/diagnostic\s*settings?/.test(text)) { symbols.add("create_diagnostic_settings"); }
  return [...symbols];
}

function repoFileRoutingScore(filePath: string, content: string, prompt: string): number {
  let score = 0;
  const normalizedFilePath = filePath.replace(/\\/g, "/").toLowerCase();
  for (const explicitPath of explicitIaCPathsFromPrompt(prompt)) {
    const requested = explicitPath.toLowerCase();
    if (normalizedFilePath === requested) { score += 10000; }
    else if (normalizedFilePath.endsWith(`/${requested}`)) { score += 9000; }
    else if (normalizedFilePath.split("/").pop() === requested.split("/").pop()) {
      score += 5000 + promptEnvironmentScore(filePath, prompt);
    }
  }
  score += resourceFamilyEvidenceScore(filePath, content, prompt);
  const normalizedPath = filePath.toLowerCase();
  for (const symbol of routingSymbolsFromPrompt(prompt)) {
    const assignment = new RegExp(`^\\s*${symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*=`, "mi");
    if (assignment.test(content)) { score += 1000; }
    if (normalizedPath.includes(symbol)) { score += 100; }
  }
  // tier.tfvars is the repository-wide feature-flag/value tier. hub.tfvars is
  // not preferred merely because it is the active editor. Exact assignment
  // evidence always dominates this small convention score.
  if (normalizedPath.endsWith("/tier.tfvars")) { score += 20; }
  return score;
}

// Step 10: repository-evidence-first context collection. Exact assignment
// ownership is collected before prompt path matches and open editor tabs.
// Editor state remains useful context, but it never decides the target file.
async function collectRepoContext(root: string, prompt: string = ""): Promise<Array<{ path: string; content: string }>> {
  const include = "**/{*.tf,*.tfvars,*.hcl,*.yaml,*.yml,*.json,*.md,terragrunt.hcl}";
  const exclude = "**/{.terraform,node_modules,.git,dist,out,build,.venv,venv,__pycache__}/**";

  const picked = new Map<string, vscode.Uri>();
  const addUri = (uri: vscode.Uri) => {
    if (uri.scheme === "file" && uri.fsPath.startsWith(root) && !picked.has(uri.fsPath)) {
      picked.set(uri.fsPath, uri);
    }
  };

  const all = await vscode.workspace.findFiles(include, exclude);
  const symbols = routingSymbolsFromPrompt(prompt);
  const cachedContent = new Map<string, string>();

  const openDocuments = new Map<string, vscode.TextDocument>();
  for (const document of vscode.workspace.textDocuments) {
    if (document.uri.scheme === "file" && document.uri.fsPath.startsWith(root)) {
      openDocuments.set(document.uri.fsPath, document);
    }
  }

  const readCandidate = async (uri: vscode.Uri): Promise<string | undefined> => {
    if (cachedContent.has(uri.fsPath)) { return cachedContent.get(uri.fsPath); }
    try {
      const openDocument = openDocuments.get(uri.fsPath);
      if (openDocument) {
        const content = openDocument.getText();
        if (Buffer.byteLength(content, "utf8") > MAX_FILE_BYTES) { return undefined; }
        cachedContent.set(uri.fsPath, content);
        return content;
      }
      const stat = await vscode.workspace.fs.stat(uri);
      if (stat.size > MAX_FILE_BYTES) { return undefined; }
      const bytes = await vscode.workspace.fs.readFile(uri);
      const content = Buffer.from(bytes).toString("utf8");
      cachedContent.set(uri.fsPath, content);
      return content;
    } catch {
      return undefined;
    }
  };

  // P-1: user-explicit file paths are binding routing evidence. Add exact
  // repo-relative paths first; for a basename such as hub.tfvars, include all
  // matching files and let environment scoring place the requested one first.
  const explicitPaths = explicitIaCPathsFromPrompt(prompt);
  for (const requested of explicitPaths) {
    const normalizedRequested = requested.toLowerCase();
    for (const uri of all) {
      const rel = path.relative(root, uri.fsPath).replace(/\\/g, "/").toLowerCase();
      if (rel === normalizedRequested || rel.endsWith(`/${normalizedRequested}`)) { addUri(uri); }
      else if (!normalizedRequested.includes("/") && rel.split("/").pop() === normalizedRequested) { addUri(uri); }
    }
  }

  // P0: exact repository ownership. Scan candidate files for exact root-level
  // assignments before considering editor state. This guarantees that a file
  // such as tier.tfvars is included when it owns the requested variable, even
  // when hub.tfvars or another unrelated file is currently active.
  if (symbols.length) {
    for (const uri of all) {
      const content = await readCandidate(uri);
      if (content === undefined) { continue; }
      const ownsRequestedAssignment = symbols.some(symbol => {
        const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        return new RegExp(`^\\s*${escaped}\\s*=`, "mi").test(content);
      });
      if (ownsRequestedAssignment) { addUri(uri); }
    }
  }

  // P0.4: AWS creation-pattern evidence. For explicit AWS creation,
  // especially clone/mirror requests, include the COMPLETE matching module
  // implementation and the target environment's consumer/value files before
  // active editors or the generic MAX_FILES walk. This ensures Foundry sees
  // every .tf file from a reference module such as redshift/auditdb plus the
  // environment main.tf it must extend.
  if (isAwsResourceCreationPrompt(prompt)) {
    const terms = awsResourceFamilyTermsFromPrompt(prompt);
    const moduleDirs = new Map<string, number>();
    const envCandidates: Array<{ uri: vscode.Uri; score: number }> = [];

    for (const uri of all) {
      const rel = path.relative(root, uri.fsPath).replace(/\\/g, "/");
      const relLower = rel.toLowerCase();
      const content = await readCandidate(uri);
      if (content === undefined) { continue; }
      const contentLower = content.toLowerCase();

      const modulesIndex = relLower.indexOf("terraform/modules/");
      if (modulesIndex >= 0 && relLower.endsWith(".tf")) {
        const after = rel.slice(modulesIndex + "terraform/modules/".length);
        const parts = after.split("/");
        if (parts.length >= 2) {
          // Keep nested modules such as redshift/auditdb together.
          const filename = parts[parts.length - 1];
          const moduleDir = rel.slice(0, rel.length - filename.length - 1);
          let score = 0;
          for (const term of terms) {
            if (moduleDir.toLowerCase().includes(term)) { score += 1200; }
            if (contentLower.includes(term)) { score += 300; }
          }
          if (isAwsCloneOrMirrorPrompt(prompt) && /\bauditdb\b/i.test(prompt) && moduleDir.toLowerCase().includes("auditdb")) {
            score += 10000;
          }
          if (score > 0) {
            moduleDirs.set(moduleDir, Math.max(moduleDirs.get(moduleDir) || 0, score));
          }
        }
      }

      if (relLower.endsWith(".tf") || relLower.endsWith(".tfvars")) {
        const envScore = promptEnvironmentScore(rel, prompt);
        if (envScore > 0) {
          const base = relLower.split("/").pop() || "";
          const typeBoost =
            base === "main.tf" ? 5000 :
            base === "variables.tf" || base === "vars.tf" ? 1800 :
            base.endsWith(".tfvars") ? 1600 : 600;
          envCandidates.push({ uri, score: typeBoost + envScore });
        }
      }
    }

    const selectedModuleDirs = [...moduleDirs.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, isAwsCloneOrMirrorPrompt(prompt) ? 2 : 3)
      .map(([dir]) => dir.toLowerCase());

    for (const moduleDir of selectedModuleDirs) {
      for (const uri of all) {
        const rel = path.relative(root, uri.fsPath).replace(/\\/g, "/").toLowerCase();
        if (rel.startsWith(moduleDir + "/") && rel.endsWith(".tf")) {
          addUri(uri);
        }
      }
    }

    envCandidates.sort((a, b) => b.score - a.score);
    for (const candidate of envCandidates.slice(0, 24)) { addUri(candidate.uri); }
  }

  // P0.5: creation-pattern evidence. For new Azure resources, load the
  // closest existing sibling definitions plus the target environment's
  // variables/value files BEFORE active editors or the generic file walk.
  // This gives Foundry enough grounded evidence to answer placement, module
  // source, ingress/networking, and tfvars questions itself instead of asking
  // the user for repository details.
  if (isAzureResourceCreationPrompt(prompt)) {
    const familyCandidates: Array<{ uri: vscode.Uri; score: number }> = [];
    const companionCandidates: Array<{ uri: vscode.Uri; score: number }> = [];
    for (const uri of all) {
      const content = await readCandidate(uri);
      if (content === undefined) { continue; }
      const rel = path.relative(root, uri.fsPath).replace(/\\/g, "/");
      const familyScore = resourceFamilyEvidenceScore(rel, content, prompt);
      if (familyScore > 0) { familyCandidates.push({ uri, score: familyScore }); }
      if (isTargetEnvironmentCompanionFile(rel, prompt)) {
        const base = rel.split("/").pop()?.toLowerCase() || "";
        const companionBoost = base === "hub.tfvars" ? 5000 : base === "variables.tf" ? 4500 : 3500;
        companionCandidates.push({ uri, score: companionBoost + promptEnvironmentScore(rel, prompt) });
      }
    }
    familyCandidates.sort((a, b) => b.score - a.score);
    companionCandidates.sort((a, b) => b.score - a.score);
    for (const candidate of familyCandidates.slice(0, 16)) { addUri(candidate.uri); }
    for (const candidate of companionCandidates.slice(0, 12)) { addUri(candidate.uri); }
  }

  // P1: explicit path/name evidence from the prompt.
  const words = prompt.toLowerCase().split(/[^a-z0-9_\-]+/).filter(w => w.length > 3);
  if (words.length) {
    for (const uri of all) {
      if (picked.size >= MAX_FILES) { break; }
      const rel = path.relative(root, uri.fsPath).toLowerCase();
      if (words.some(w => rel.includes(w))) { addUri(uri); }
    }
  }

  // P2: open editor tabs remain useful context, but they are not treated as
  // authoritative routing evidence and cannot displace exact assignment owners.
  const active = vscode.window.activeTextEditor?.document?.uri;
  if (active) { addUri(active); }
  for (const group of vscode.window.tabGroups.all) {
    for (const tab of group.tabs) {
      const input: any = tab.input;
      if (input && input.uri instanceof vscode.Uri) { addUri(input.uri); }
    }
  }

  // P3: fill the remaining context budget with the general repository walk.
  for (const uri of all) {
    if (picked.size >= MAX_FILES) { break; }
    addUri(uri);
  }

  const files: Array<{ path: string; content: string }> = [];
  for (const uri of picked.values()) {
    if (files.length >= MAX_FILES) { break; }
    const content = await readCandidate(uri);
    if (content === undefined) { continue; }
    files.push({
      path: path.relative(root, uri.fsPath).replace(/\\/g, "/"),
      content,
    });
  }

  files.sort((left, right) =>
    repoFileRoutingScore(right.path, right.content, prompt) - repoFileRoutingScore(left.path, left.content, prompt)
  );
  return files;
}

// ── virtual document helper (kept for scan / explain-workflow) ───────────────

async function showVirtualDocument(content: string, language: string): Promise<void> {
  const doc = await vscode.workspace.openTextDocument({ content, language });
  await vscode.window.showTextDocument(doc, { preview: false });
}

// ── scan (unchanged) ─────────────────────────────────────────────────────────

async function scanRepository(): Promise<void> {
  const root = await getWorkspaceRoot();
  const aiEndpoint = getAiEndpoint();
  if (aiEndpoint) {
    const files = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "Terrabot collecting repository context..." },
      () => collectRepoContext(root)
    );
    await showVirtualDocument(JSON.stringify({ workspace: root, files }, null, 2), "json");
    return;
  }
  const result = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Terrabot scanning repository..." },
    () => runTerrabot(["scan", "--workspace", root, "--json"], root)
  );
  await showVirtualDocument(result, "json");
}

// ── explain-workflow (unchanged) ─────────────────────────────────────────────

async function explainWorkflow(prompt?: string): Promise<string> {
  const root = await getWorkspaceRoot();
  const resolvedPrompt = prompt || await vscode.window.showInputBox({
    title: "Terrabot Workflow Prompt",
    prompt: "Describe the infrastructure request to explain."
  });
  if (!resolvedPrompt) { return "No prompt provided."; }
  const aiEndpoint = getAiEndpoint();
  if (aiEndpoint) {
    const files = await collectRepoContext(root, resolvedPrompt);
    const result = await postJson(`${getBackendBaseUrl()}/api/vscode/explain-workflow`, {
      prompt: resolvedPrompt,
      workspace_name: path.basename(root),
      files
    });
    return JSON.stringify(result.result || result, null, 2);
  }
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Terrabot inferring workflow..." },
    () => runTerrabot(["explain-workflow", "--workspace", root, "--json", resolvedPrompt], root)
  );
}

// ── Step 7: validation terminal helper ───────────────────────────────────────

async function runValidation(root: string, commands: string[]): Promise<void> {
  if (!commands.length) { return; }

  const terminal = vscode.window.createTerminal({
    name: "Terrabot Validation",
    cwd: root,
  });
  terminal.show(true);

  for (const cmd of commands) {
    terminal.sendText(cmd);
  }
}

// ── Step 11: live editor typing effect ──────────────────────────────────────
// Animate the smallest changed range of every generated create/modify file.
// This lets users watch Terrabot write directly in the active editor while the
// chat participant reports which file is being written. The final content is
// still backend-validated; this is only the application mechanism.
async function applyLiveFileEdit(
  root: string,
  file: { path: string; operation: string; content?: string },
): Promise<boolean> {
  if (file.operation !== "create" && file.operation !== "modify") { return false; }

  const cleanedPath = file.path.replace(/^\/tmp\/terrabot[^/]+\/[^/]+\//, "");
  const absPath = path.isAbsolute(cleanedPath) ? cleanedPath : path.join(root, cleanedPath);
  const uri = vscode.Uri.file(absPath);
  const finalContent = file.content ?? "";

  let doc: vscode.TextDocument;
  try {
    doc = await vscode.workspace.openTextDocument(uri);
  } catch {
    try {
      const createEdit = new vscode.WorkspaceEdit();
      createEdit.createFile(uri, { overwrite: false, ignoreIfExists: true });
      if (!await vscode.workspace.applyEdit(createEdit)) { return false; }
      doc = await vscode.workspace.openTextDocument(uri);
    } catch { return false; }
  }

  const editor = await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: false });
  const current = doc.getText();
  if (current === finalContent) { return true; }

  let prefix = 0;
  const maxPrefix = Math.min(current.length, finalContent.length);
  while (prefix < maxPrefix && current[prefix] === finalContent[prefix]) { prefix++; }

  let suffix = 0;
  while (
    suffix < current.length - prefix &&
    suffix < finalContent.length - prefix &&
    current[current.length - 1 - suffix] === finalContent[finalContent.length - 1 - suffix]
  ) { suffix++; }

  const oldEndOffset = current.length - suffix;
  const newText = finalContent.slice(prefix, finalContent.length - suffix);
  const startPos = doc.positionAt(prefix);
  const endPos = doc.positionAt(oldEndOffset);
  editor.revealRange(new vscode.Range(startPos, endPos), vscode.TextEditorRevealType.InCenter);

  const deleted = await editor.edit(
    edit => edit.delete(new vscode.Range(startPos, endPos)),
    { undoStopBefore: true, undoStopAfter: false },
  );
  if (!deleted) { return false; }

  // Small edits type character-by-character. Larger generated blocks use small
  // chunks so the animation stays visible without taking minutes.
  const chunkSize = newText.length <= 800 ? 1 : newText.length <= 6000 ? 6 : 32;
  const delayMs = newText.length <= 800 ? 16 : newText.length <= 6000 ? 9 : 4;
  let pos = startPos;
  for (let offset = 0; offset < newText.length; offset += chunkSize) {
    const chunk = newText.slice(offset, offset + chunkSize);
    const inserted = await editor.edit(
      edit => edit.insert(pos, chunk),
      { undoStopBefore: false, undoStopAfter: false },
    );
    if (!inserted) { return false; }
    pos = doc.positionAt(doc.offsetAt(pos) + chunk.length);
    editor.selection = new vscode.Selection(pos, pos);
    editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    await new Promise<void>(resolve => setTimeout(resolve, delayMs));
  }

  await doc.save();
  return true;
}

// ── Step 6 + 7: apply generated files via WorkspaceEdit ──────────────────────

async function applyGeneratedFiles(
  root: string,
  files: Array<{ path: string; operation: string; content?: string; in_place?: boolean; typed_insert?: unknown; typed_replacements?: Array<{ token: string; value: string }> }>,
  summary: string,
  validationCommands: string[] = [],   // Step 7
  onWriting?: (filePath: string) => void,
  openSourceControl: boolean = true,
): Promise<void> {
  const edit = new vscode.WorkspaceEdit();
  const remaining: typeof files = [];

  // Step 11: animate generated creates/modifications in the real editor.
  // Any unsupported or failed case falls through to the existing safe
  // WorkspaceEdit path, so application semantics remain unchanged.
  for (const file of files) {
    if (file.operation === "create" || file.operation === "modify") {
      onWriting?.(file.path);
      const typed = await applyLiveFileEdit(root, file);
      if (typed) { continue; }
    }
    remaining.push(file);
  }

  for (const file of remaining) {
    // Strip temp-dir prefixes that the backend may have leaked into paths.
    // repo-relative paths (terraform/main.tf) are left untouched.
    const cleanedPath = file.path.replace(/^\/tmp\/terrabot[^/]+\/[^/]+\//, "");

    const absPath = path.isAbsolute(cleanedPath)
      ? cleanedPath
      : path.join(root, cleanedPath);

    const uri = vscode.Uri.file(absPath);

    if (file.operation === "delete") {
      edit.deleteFile(uri, { ignoreIfNotExists: true });
      continue;
    }

    const content = file.content ?? "";

    if (file.operation === "create") {
      // createFile + insert guarantees the file exists before we write to it.
      edit.createFile(uri, { overwrite: false, ignoreIfExists: false });
      edit.insert(uri, new vscode.Position(0, 0), content);
    } else {
      // modify — replace entire file content, WITH a shrink guard:
      // if the new content does not contain the existing content as a prefix
      // (i.e. it would delete existing code), append instead of replacing.
      // The backend enforces the same contract; this is the last line of
      // defense so a destructive payload can never wipe a user's file.
      try {
        await vscode.workspace.fs.stat(uri);
        const existingBytes = await vscode.workspace.fs.readFile(uri);
        const existing = Buffer.from(existingBytes).toString("utf8");
        const normExisting = existing.replace(/\s+$/, "");
        const normNew = content.replace(/\s+$/, "");

        if (normNew.startsWith(normExisting) || existing.trim() === "" || file.in_place || (file as any).typed_insert) {
          // Valid append-contract content, an explicit in-place edit, or a
          // backend-expanded typed insert/fill. Full replace is safe here;
          // appending non-prefix content would duplicate existing Terraform.
          const fullRange = new vscode.Range(
            new vscode.Position(0, 0),
            new vscode.Position(Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER)
          );
          edit.replace(uri, fullRange, content);
        } else {
          // Refuse unsafe non-prefix content. Do not append it: appending was
          // the source of doubled provider/module blocks in large .tf files.
          vscode.window.showErrorMessage(
            `Terrabot blocked an unsafe edit for ${cleanedPath}: generated content was not a prefix-preserving append or typed insert. No duplicate code was appended.`
          );
        }
      } catch {
        // File does not exist yet — create it.
        edit.createFile(uri, { overwrite: true });
        edit.insert(uri, new vscode.Position(0, 0), content);
      }
    }
  }

  if (remaining.length) {
    const applied = await vscode.workspace.applyEdit(edit);
    if (!applied) {
      vscode.window.showErrorMessage("Terrabot: WorkspaceEdit failed — no changes were applied.");
      return;
    }
  }

  // Opening SCM starts a Git refresh. Defer it during a combined generate+PR
  // request so VS Code cannot race Terrabot's stash/add/commit index writes.
  if (openSourceControl) {
    await vscode.commands.executeCommand("workbench.view.scm");
  }

  // Step 7: offer to run repo-native validation commands.
  const action = await vscode.window.showInformationMessage(
    `Terrabot applied ${files.length} file(s). ${summary}`,
    "Run Validation",
    "Dismiss"
  );
  if (action === "Run Validation") {
    await runValidation(root, validationCommands);
  }
}

// ── Step 6: askInfrastructure — now returns void, uses WorkspaceEdit ─────────

async function askInfrastructure(prompt?: string): Promise<void> {
  if (!vscode.workspace.isTrusted) {
    vscode.window.showWarningMessage("Terrabot generation requires a trusted workspace.");
    return;
  }

  const root = await getWorkspaceRoot();
  const resolvedPrompt = prompt || await vscode.window.showInputBox({
    title: "Terrabot Infrastructure Request",
    prompt: "Describe the infrastructure change you want.",
  });
  if (!resolvedPrompt) { return; }

  const aiEndpoint = getAiEndpoint();

  // Step 9: Command Palette shares the session thread; reset only on
  // workspace switch (history length 1 keeps the current thread alive).
  resetThreadIfNeeded(root, 1);

  // ── Hosted path: POST to /api/generate then apply via WorkspaceEdit ──
  const repository = await resolveGitContext(root);
  const result = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Terrabot generating changes..." },
    async () => postJson(aiEndpoint, {
      prompt: resolvedPrompt,
      workspace_name: path.basename(root),
      thread_id: currentThreadId,               // Step 9: continuity
      repository,                               // shared repository-context identity
      files: await collectRepoContext(root, resolvedPrompt),  // Step 10
    })
  );

  if (result.thread_id) {
    currentThreadId = String(result.thread_id);  // Step 9: persist
  }

  const files: Array<{ path: string; operation: string; content?: string }> = result.files || [];
  if (!files.length) {
    vscode.window.showInformationMessage(
      result.reply || result.summary || "No files were generated."
    );
    return;
  }

  await applyGeneratedFiles(
    root,
    files,
    result.summary || result.reply || "",
    result.validation_commands || [],
  );
}

// ── Step 8 + 9: @terrabot chat participant — unified pipeline ─────────────────

function registerChatParticipant(context: vscode.ExtensionContext): void {
  const chatApi = (vscode as any).chat;
  if (!chatApi || typeof chatApi.createChatParticipant !== "function") { return; }

  const participant = chatApi.createChatParticipant(
    "terrabot.infra",
    async (request: any, chatContext: any, stream: any) => {
      const prompt: string = request.prompt || "";
      const command: string = request.command || "plan";

      if (!prompt) {
        stream.markdown("Please provide a description of the infrastructure change you want.");
        return;
      }

      try {
        const root = await getWorkspaceRoot(); 

        const wantsPullRequest = isPullRequestPrompt(prompt);
        const wantsBranch = isBranchPrompt(prompt);

        // A branch-only command is handled directly. Combined requests such as
        // "disable CloudAMQP, create a branch, and raise a PR" continue through
        // generation first, then branch creation, commit/push, and PR creation.
        if (isBranchPrompt(prompt) && !wantsPullRequest && isPureBranchPrompt(prompt)) {
          stream.progress("Preparing the requested GitHub branch...");
          await ensureWorkspaceChangeBranch(root, prompt, false);
          const branchContext = await resolveGitContext(root);
          const githubAuth = await connectGitHubAccount();
          await runGitAuthenticated(["push", "-u", "origin", branchContext.branch], root, githubAuth.token);
          const branchUrl = `https://github.com/${branchContext.owner}/${branchContext.repo}/tree/${branchContext.branch}`;
          const compareUrl = `https://github.com/${branchContext.owner}/${branchContext.repo}/compare/${branchContext.base}...${branchContext.branch}`;
          stream.markdown(`GitHub branch ready: [${branchContext.branch}](${branchUrl})\n\n[Compare ${branchContext.branch} with ${branchContext.base}](${compareUrl})`);
          return;
        }

        if (wantsPullRequest && isPurePullRequestPrompt(prompt)) {
          stream.progress("Committing changes, pushing the branch, and creating the draft pull request...");
          const forceSeparate = isSeparatePullRequestPrompt(prompt);
          if (isSamePullRequestPrompt(prompt) && currentWorkspacePrBranch) {
            const current = await resolveGitContext(root);
            if (current.branch !== currentWorkspacePrBranch) {
              await runCommand("git", ["checkout", currentWorkspacePrBranch], root);
            }
          }
          const created = await createPullRequestFromWorkspace(root, prompt, forceSeparate, (message: string) => stream.progress(message));
          stream.markdown(`${created.existing ? "Existing draft PR updated" : "GitHub draft PR created"}: [Open pull request](${created.prUrl})\n\n[Compare ${created.branch} with main](${created.compareUrl})\n\n**Terrabot Git resolution:**\n${created.notes.map(note => `- ${note}`).join("\n")}`);
          return;
        }

        // ── explain-workflow command: show JSON in chat, no file edits ──
        if (command === "explain-workflow") {
          const result = await explainWorkflow(prompt);
          stream.markdown("```json\n" + result + "\n```");
          return;
        }

        const preparedGitTarget = await prepareGitTargetBeforeGeneration(
          root,
          prompt,
          wantsPullRequest,
          wantsBranch,
          (message: string) => stream.progress(message),
        );

        const aiEndpoint = getAiEndpoint();

        // Step 9: new chat session (empty history) or workspace switch →
        // start a fresh Foundry conversation. Otherwise keep the thread so
        // the agent remembers earlier prompts and the user's answers.
        const historyLength: number = (chatContext && chatContext.history)
          ? chatContext.history.length
          : 0;
        resetThreadIfNeeded(root, historyLength);

        // Neutral progress indicator — never announce "generating changes"
        // before intent is known (the message may be chat or a question).
        stream.progress("Terrabot is thinking...");

        // ── Hosted path: same /api/generate call as Command Palette ──
        const repository = await resolveGitContext(root);
        const result = await postJson(aiEndpoint, {
          prompt,
          workspace_name: path.basename(root),
          thread_id: currentThreadId,             // Step 9: continuity
          repository,                             // shared repository-context identity
          files: await collectRepoContext(root, prompt),  // Step 10
        });

        // Step 9: persist the conversation id for following turns.
        if (result.thread_id) {
          currentThreadId = String(result.thread_id);
        }

        const files: Array<{ path: string; operation: string; content?: string }> = result.files || [];

        // Show the agent's visible thinking (repo analysis) when present.
        const analysis: string = result.analysis || "";
        if (analysis) {
          stream.markdown(
            "*Terrabot's analysis:*\n\n" +
            analysis.split("\n").map((l: string) => `> ${l}`).join("\n") +
            "\n\n"
          );
        }

        if (!files.length) {
          // Chat / repo Q&A / clarification path — render the agent's words directly.
          const replyText: string = result.reply || result.summary || "";
          if (replyText) {
            stream.markdown(replyText);
          }
          // Render clarifying questions as a list when present.
          const questions: string[] = result.questions || [];
          if (questions.length) {
            stream.markdown("\n\n" + questions.map((q: string) => `- ${q}`).join("\n"));
          }
          if (!replyText && !questions.length) {
            stream.markdown("I didn't produce any changes. Could you rephrase your request?");
          }
          return;
        }

        // Apply files to the workspace (same helper as Command Palette — Step 6 + 7).
        await applyGeneratedFiles(
          root,
          files,
          result.summary || result.reply || "",
          result.validation_commands || [],
          (filePath: string) => stream.progress(`Terrabot is writing ${filePath}...`),
          !(wantsPullRequest || wantsBranch),
        );

        // Report back in the chat panel.
        const fileList = files
          .map(f => `- \`${f.path}\` (${f.operation})`)
          .join("\n");

        stream.markdown(
          `**Applied ${files.length} file(s)** to your workspace:\n\n${fileList}\n\n` +
          `${result.summary || ""}\n\n` +
          `Check the **Source Control** panel to review the diff before committing.`
        );

        if (wantsPullRequest) {
          stream.progress("Committing the generated changes, pushing the branch, and creating the draft pull request...");
          const forceSeparate = isSeparatePullRequestPrompt(prompt);
          const created = await createPullRequestFromWorkspace(
            root,
            prompt,
            forceSeparate,
            (message: string) => stream.progress(message),
            preparedGitTarget,
          );
          await vscode.commands.executeCommand("workbench.view.scm");
          stream.markdown(`\n\n${created.existing ? "Existing draft PR updated" : "GitHub draft PR created"}: [Open pull request](${created.prUrl})\n\n[Compare ${created.branch} with main](${created.compareUrl})\n\n**Terrabot Git resolution:**\n${created.notes.map(note => `- ${note}`).join("\n")}`);
        }
        else if (wantsBranch) {
          stream.progress("Committing the generated infrastructure changes and pushing the requested branch...");
          const pushed = await pushWorkspaceChangesToBranch(
            root,
            prompt,
            (message: string) => stream.progress(message),
            preparedGitTarget,
          );
          await vscode.commands.executeCommand("workbench.view.scm");
          stream.markdown(`\n\nGitHub branch updated: [${pushed.branch}](${pushed.branchUrl})\n\n[Compare ${pushed.branch} with main](${pushed.compareUrl})\n\n**Terrabot Git resolution:**\n${pushed.notes.map(note => `- ${note}`).join("\n")}`);
        }

        // List fill-in values the user should complete (search for __FILL__ tokens).
        const fillable: Array<{ token: string; input: string; file: string; hint?: string }> =
          result.user_fillable || [];
        if (fillable.length) {
          const fillList = fillable
            .map(f => `- \`${f.token}\` in \`${f.file}\` — ${f.hint || f.input}`)
            .join("\n");
          stream.markdown(
            `\n\n**Fill in these values** (search for \`__FILL__\` in the files):\n\n${fillList}`
          );
        }

      } catch (err) {
        stream.markdown(
          `Terrabot failed: ${err instanceof Error ? err.message : String(err)}`
        );
      }
    }
  );

  context.subscriptions.push(participant);
}

// ── activate ──────────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
  extensionContext = context;
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "terrabot.scanRepository",
      scanRepository
    ),

    vscode.commands.registerCommand(
      "terrabot.explainWorkflow",
      async () =>
        showVirtualDocument(
          await explainWorkflow(),
          "json"
        )
    ),

    vscode.commands.registerCommand(
      "terrabot.askInfrastructure",
      () => askInfrastructure()
    ),

    vscode.commands.registerCommand(
      "terrabot.connectGitHub",
      async () => {
        const auth = await connectGitHubAccount();
        vscode.window.showInformationMessage(`Terrabot connected to GitHub as ${auth.account}.`);
      }
    ),

    vscode.commands.registerCommand(
      "terrabot.disconnectGitHub",
      disconnectGitHubAccount
    ),

    vscode.commands.registerCommand(
      "terrabot.openStandaloneChat",
      async () => {
        const prompt = await vscode.window.showInputBox({
          title: "Terrabot",
          prompt: "Describe the infrastructure change you want.",
          placeHolder:
            "Example: Disable patch management in sbx-infra",
          ignoreFocusOut: true,
        });

        if (!prompt?.trim()) {
          return;
        }

        await askInfrastructure(prompt.trim());
      }
    ),
  );

  // Keep the existing @terrabot chat participant.
  registerChatParticipant(context);
}

export function deactivate(): void {}
