#!/usr/bin/env node
import { createServer } from "node:http";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname, resolve as resolvePath } from "node:path";
import { spawn } from "node:child_process";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function run(command, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      ...options,
      stdio: ["ignore", "pipe", "pipe"],
    });

    const stdoutChunks = [];
    const stderrChunks = [];

    child.stdout.on("data", (chunk) => stdoutChunks.push(Buffer.from(chunk)));
    child.stderr.on("data", (chunk) => stderrChunks.push(Buffer.from(chunk)));
    child.on("error", rejectPromise);
    child.on("close", (code) => {
      resolvePromise({
        code,
        stdout: Buffer.concat(stdoutChunks).toString("utf8"),
        stderr: Buffer.concat(stderrChunks).toString("utf8"),
      });
    });
  });
}

async function setupFakeServer() {
  const root = await mkdtemp(join(tmpdir(), "azdo-vargroup-get-test-"));

  const server = createServer((req, res) => {
    const url = new URL(req.url || "", "http://127.0.0.1");

    if (!url.pathname.includes("/_apis/distributedtask/variablegroups")) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    const groupName = url.searchParams.get("groupName");
    const groupIds = url.searchParams.get("groupIds");

    if (groupName === "app-secrets" || groupIds === "10") {
      res.statusCode = 200;
      res.setHeader("Content-Type", "application/json");
      res.end(
        JSON.stringify({
          count: 1,
          value: [
            {
              id: 10,
              name: "app-secrets",
              description: "Variables used by the deploy pipeline",
              type: "Vsts",
              variables: {
                apiUrl: { value: "https://example.local" },
                token: { isSecret: true, value: "***" },
              },
            },
          ],
        }),
      );
      return;
    }

    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ count: 0, value: [] }));
  });

  await new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", () => resolvePromise(undefined));
  });

  const address = server.address();
  if (typeof address !== "object" || !address || !address.port) {
    throw new Error("Failed to resolve fake server port.");
  }

  const baseUrl = `http://127.0.0.1:${address.port}`;

  return { root, server, baseUrl };
}

async function main() {
  const thisDir = dirname(fileURLToPath(import.meta.url));
  const skillDir = resolvePath(thisDir, "..");
  const scriptPath = resolvePath(skillDir, "azdo-vargroup-get.mjs");

  const { root, server, baseUrl } = await setupFakeServer();
  let passed = false;

  try {
    const repoDir = join(root, "repo");
    await mkdir(repoDir, { recursive: true });
    await run("git", ["init"], { cwd: repoDir });
    await run("git", ["remote", "add", "origin", `${baseUrl}/DefaultCollection/TestProject/_git/TestRepo`], {
      cwd: repoDir,
    });

    const env = {
      ...process.env,
      AZDO_PAT: "dummy-pat",
    };

    // Case 1: by name
    const byNameResult = await run(process.execPath, [scriptPath, "--name", "app-secrets"], { cwd: repoDir, env });
    assert(
      byNameResult.code === 0,
      `Expected exit code 0 for vargroup get by name, got ${byNameResult.code}. STDERR: ${byNameResult.stderr}`,
    );
    let byNamePayload;
    try {
      byNamePayload = JSON.parse(byNameResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse vargroup get by name payload as JSON: ${error?.message || String(byNameResult.stdout)}`,
      );
    }
    assert(byNamePayload.ok === true, "Expected ok true for vargroup get by name.");
    assert(byNamePayload.group.id === 10, `Expected group id 10, got ${byNamePayload.group.id}`);

    // Case 2: by id
    const byIdResult = await run(process.execPath, [scriptPath, "--id", "10"], { cwd: repoDir, env });
    assert(
      byIdResult.code === 0,
      `Expected exit code 0 for vargroup get by id, got ${byIdResult.code}. STDERR: ${byIdResult.stderr}`,
    );
    let byIdPayload;
    try {
      byIdPayload = JSON.parse(byIdResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse vargroup get by id payload as JSON: ${error?.message || String(byIdResult.stdout)}`,
      );
    }
    assert(byIdPayload.ok === true, "Expected ok true for vargroup get by id.");
    assert(byIdPayload.group.id === 10, `Expected group id 10, got ${byIdPayload.group.id}`);

    // Case 3: missing group
    const missingResult = await run(process.execPath, [scriptPath, "--name", "missing"], { cwd: repoDir, env });
    assert(
      missingResult.code === 4,
      `Expected exit code 4 for missing vargroup, got ${missingResult.code}. STDERR: ${missingResult.stderr}`,
    );
    let missingPayload;
    try {
      missingPayload = JSON.parse(missingResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse missing vargroup payload as JSON: ${error?.message || String(missingResult.stdout)}`,
      );
    }
    assert(missingPayload.ok === false, "Expected ok false for missing vargroup.");
    assert(missingPayload.reason === "not-found", `Expected reason not-found, got ${missingPayload.reason}`);

    passed = true;
    process.stdout.write("PASS azdo-vargroup-get smoke test\n");
  } finally {
    server.close();
    if (passed) {
      await rm(root, { recursive: true, force: true });
    } else {
      process.stderr.write(`Preserved temp test root for inspection: ${root}\n`);
    }
  }
}

main().catch((error) => {
  process.stderr.write(`FAIL azdo-vargroup-get smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
