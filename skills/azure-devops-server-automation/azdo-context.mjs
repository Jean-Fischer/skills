#!/usr/bin/env node
import { spawn } from "node:child_process";
import { access, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import { join, resolve as resolvePath } from "node:path";
import { URL } from "node:url";

function fileExists(path) {
  return access(path, constants.F_OK)
    .then(() => true)
    .catch(() => false);
}

async function readSidecarConfig(repoDir) {
  const sidecarPath = resolvePath(repoDir, ".azdo-context.json");
  if (!(await fileExists(sidecarPath))) {
    return null;
  }

  const raw = await readFile(sidecarPath, "utf8");
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error(
      `Sidecar config ${sidecarPath} is not valid JSON: ${error?.message || String(
        error,
      )}`,
    );
  }

  const { baseUrl, collection, project, repository } = parsed;
  if (!baseUrl || !collection || !project || !repository) {
    throw new Error(
      `Sidecar config ${sidecarPath} must include baseUrl, collection, project, and repository fields.`,
    );
  }

  return { baseUrl, collection, project, repository, sidecarPath };
}

async function getGitRemoteUrl(repoDir, remoteName = "origin") {
  return new Promise((resolvePromise) => {
    const child = spawn("git", ["remote", "get-url", remoteName], {
      cwd: repoDir,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });

    child.on("close", (code) => {
      if (code !== 0) {
        resolvePromise({
          url: null,
          error: new Error(
            stderr.trim() || stdout.trim() || `git remote get-url ${remoteName} failed with code ${code}`,
          ),
        });
      } else {
        resolvePromise({ url: stdout.trim(), error: null });
      }
    });
  });
}

function parseAzureDevOpsServerRemote(remoteUrl) {
  let url;
  try {
    url = new URL(remoteUrl);
  } catch {
    return null;
  }

  const hostname = url.hostname.toLowerCase();

  // Reject known non-server hosts and Azure DevOps Services hosts.
  if (hostname === "github.com" || hostname.endsWith(".github.com")) {
    return null;
  }
  if (hostname === "dev.azure.com" || hostname.endsWith(".visualstudio.com")) {
    // Azure DevOps Services (cloud) is out of scope for this skill.
    return null;
  }

  const segments = url.pathname.split("/").filter(Boolean);
  const gitIndex = segments.indexOf("_git");
  if (gitIndex === -1 || gitIndex + 1 >= segments.length) {
    return null;
  }

  const repo = segments[gitIndex + 1];
  const first = segments[0] || "";
  const isTfsRoot = first.toLowerCase() === "tfs";

  let root = "";
  let collection;
  let project;

  if (isTfsRoot) {
    // Shapes:
    //   /tfs/DefaultCollection/_git/MyProject
    //   /tfs/DefaultCollection/MyProject/_git/MyRepo
    root = first;
    if (gitIndex === 2 && segments.length >= 4) {
      // /tfs/{collection}/_git/{project}
      collection = segments[1];
      project = repo;
    } else if (gitIndex === 3 && segments.length >= 5) {
      // /tfs/{collection}/{project}/_git/{repo}
      collection = segments[1];
      project = segments[2];
    } else {
      return null;
    }
  } else {
    // Shapes without explicit /tfs root:
    //   /DefaultCollection/_git/MyProject
    //   /DefaultCollection/MyProject/_git/MyRepo
    root = "";
    if (gitIndex === 1 && segments.length >= 3) {
      // /{collection}/_git/{project}
      collection = segments[0];
      project = repo;
    } else if (gitIndex === 2 && segments.length >= 4) {
      // /{collection}/{project}/_git/{repo}
      collection = segments[0];
      project = segments[1];
    } else {
      return null;
    }
  }

  const basePath = root ? `/${root}` : "";
  const baseUrl = `${url.protocol}//${url.host}${basePath}`;

  return {
    baseUrl,
    collection,
    project,
    repository: repo,
    remoteUrl,
  };
}

function isCompleteContext(ctx) {
  return !!(
    ctx &&
    typeof ctx.baseUrl === "string" &&
    ctx.baseUrl &&
    typeof ctx.collection === "string" &&
    ctx.collection &&
    typeof ctx.project === "string" &&
    ctx.project &&
    typeof ctx.repository === "string" &&
    ctx.repository
  );
}

export async function resolveAzureDevOpsContext(options = {}) {
  const repoDir = options.repoDir ? resolvePath(options.repoDir) : process.cwd();

  const overrides = {
    baseUrl: options.baseUrl,
    collection: options.collection,
    project: options.project,
    repository: options.repository,
  };

  if (isCompleteContext(overrides)) {
    return { ...overrides, source: "overrides" };
  }

  let sidecar = null;
  try {
    sidecar = await readSidecarConfig(repoDir);
  } catch (error) {
    // Invalid sidecar config is a hard failure rather than falling back silently.
    throw error;
  }

  const mergedFromSidecar = {
    baseUrl: overrides.baseUrl ?? sidecar?.baseUrl,
    collection: overrides.collection ?? sidecar?.collection,
    project: overrides.project ?? sidecar?.project,
    repository: overrides.repository ?? sidecar?.repository,
  };

  if (isCompleteContext(mergedFromSidecar)) {
    return {
      ...mergedFromSidecar,
      source: sidecar ? "sidecar" : "overrides+sidecar",
      sidecarPath: sidecar?.sidecarPath,
    };
  }

  const remoteOverride = options.remote;
  let remoteInfo;
  if (remoteOverride) {
    remoteInfo = { url: remoteOverride, error: null };
  } else {
    remoteInfo = await getGitRemoteUrl(repoDir);
  }

  if (!remoteInfo.url) {
    throw remoteInfo.error || new Error("No git remote URL found for origin.");
  }

  const parsed = parseAzureDevOpsServerRemote(remoteInfo.url);
  if (!parsed) {
    throw new Error(
      "Git remote URL does not look like an Azure DevOps Server clone URL. Provide explicit overrides or an .azdo-context.json sidecar.",
    );
  }

  const final = {
    baseUrl: mergedFromSidecar.baseUrl ?? parsed.baseUrl,
    collection: mergedFromSidecar.collection ?? parsed.collection,
    project: mergedFromSidecar.project ?? parsed.project,
    repository: mergedFromSidecar.repository ?? parsed.repository,
    remoteUrl: parsed.remoteUrl,
    source: sidecar ? "sidecar+remote" : "remote",
    sidecarPath: sidecar?.sidecarPath,
  };

  if (!isCompleteContext(final)) {
    throw new Error("Resolved Azure DevOps context is incomplete after applying overrides, sidecar config, and git remote.");
  }

  return final;
}

export { parseAzureDevOpsServerRemote };
