#!/usr/bin/env node
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname, resolve as resolvePath } from "node:path";

import { resolveAzureDevOpsContext, parseAzureDevOpsServerRemote } from "../azdo-context.mjs";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function setupRepo(remoteUrl) {
  const root = await mkdtemp(join(tmpdir(), "azdo-context-test-"));
  const repoDir = join(root, "repo");
  await mkdir(repoDir, { recursive: true });

  // Minimal Git setup with origin remote only.
  const { spawn } = await import("node:child_process");
  const run = (cmd, args) =>
    new Promise((resolvePromise, rejectPromise) => {
      const child = spawn(cmd, args, { cwd: repoDir, stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString("utf8");
      });
      child.on("close", (code) => {
        if (code !== 0) {
          rejectPromise(new Error(stderr || `${cmd} ${args.join(" ")} failed with ${code}`));
        } else {
          resolvePromise();
        }
      });
    });

  await run("git", ["init"]);
  await run("git", ["remote", "add", "origin", remoteUrl]);

  return { root, repoDir };
}

async function main() {
  const skillDir = dirname(fileURLToPath(import.meta.url));
  const azureSkillDir = resolvePath(skillDir, "..");
  if (!azureSkillDir) {
    throw new Error("Skill directory resolution failed.");
  }

  const remoteUrl = "https://server/tfs/DefaultCollection/MyProject/_git/MyRepo";
  const parsed = parseAzureDevOpsServerRemote(remoteUrl);
  assert(parsed, "Expected Azure DevOps Server remote to parse correctly.");
  assert(parsed.baseUrl === "https://server/tfs", `Unexpected baseUrl ${parsed.baseUrl}`);
  assert(parsed.collection === "DefaultCollection", `Unexpected collection ${parsed.collection}`);
  assert(parsed.project === "MyProject", `Unexpected project ${parsed.project}`);
  assert(parsed.repository === "MyRepo", `Unexpected repository ${parsed.repository}`);

  const { root, repoDir } = await setupRepo(remoteUrl);
  let passed = false;

  try {
    // Write sidecar config to override project while reusing baseUrl/collection.
    const sidecarPath = join(repoDir, ".azdo-context.json");
    await writeFile(
      sidecarPath,
      JSON.stringify(
        {
          baseUrl: "https://server/tfs",
          collection: "DefaultCollection",
          project: "OverrideProject",
          repository: "OverrideRepo",
        },
        null,
        2,
      ) + "\n",
      "utf8",
    );

    const resolved = await resolveAzureDevOpsContext({ repoDir });
    assert(resolved.baseUrl === "https://server/tfs", `Resolved baseUrl mismatch: ${resolved.baseUrl}`);
    assert(resolved.collection === "DefaultCollection", `Resolved collection mismatch: ${resolved.collection}`);
    assert(resolved.project === "OverrideProject", `Resolved project mismatch: ${resolved.project}`);
    assert(resolved.repository === "OverrideRepo", `Resolved repository mismatch: ${resolved.repository}`);
    passed = true;
    process.stdout.write("PASS azdo-context smoke test\n");
  } finally {
    if (passed) {
      await rm(root, { recursive: true, force: true });
    } else {
      process.stderr.write(`Preserved temp test root for inspection: ${root}\n`);
    }
  }
}

main().catch((error) => {
  process.stderr.write(`FAIL azdo-context smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
