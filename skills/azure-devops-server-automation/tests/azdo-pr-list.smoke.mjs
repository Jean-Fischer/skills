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
  const root = await mkdtemp(join(tmpdir(), "azdo-pr-list-test-"));

  const server = createServer((req, res) => {
    const url = new URL(req.url || "", "http://127.0.0.1");

    if (!url.pathname.includes("/_apis/git/repositories") || !url.pathname.endsWith("/pullrequests")) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    const status = url.searchParams.get("searchCriteria.status") || "active";
    const sourceRefName = url.searchParams.get("searchCriteria.sourceRefName") || "refs/heads/feature/test";
    const targetRefName = url.searchParams.get("searchCriteria.targetRefName") || "refs/heads/main";

    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        count: 1,
        value: [
          {
            pullRequestId: 123,
            title: "Filtered PR",
            status,
            sourceRefName,
            targetRefName,
          },
        ],
      }),
    );
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
  const scriptPath = resolvePath(skillDir, "azdo-pr-list.mjs");

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

    // Case 1: list with no filters
    const listResult = await run(process.execPath, [scriptPath], { cwd: repoDir, env });
    assert(listResult.code === 0, `Expected exit code 0 for list, got ${listResult.code}. STDERR: ${listResult.stderr}`);
    let listPayload;
    try {
      listPayload = JSON.parse(listResult.stdout.trim());
    } catch (error) {
      throw new Error(`Failed to parse list payload as JSON: ${error?.message || String(error)}\n${listResult.stdout}`);
    }
    assert(listPayload.ok === true, "Expected ok true for list.");
    assert(listPayload.result.count === 1, `Expected count 1, got ${listPayload.result.count}`);

    // Case 2: list with filters
    const filteredResult = await run(
      process.execPath,
      [scriptPath, "--status", "completed", "--source", "refs/heads/feature/xyz", "--target", "refs/heads/release"],
      { cwd: repoDir, env },
    );
    assert(
      filteredResult.code === 0,
      `Expected exit code 0 for filtered list, got ${filteredResult.code}. STDERR: ${filteredResult.stderr}`,
    );
    let filteredPayload;
    try {
      filteredPayload = JSON.parse(filteredResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse filtered list payload as JSON: ${error?.message || String(error)}\n${filteredResult.stdout}`,
      );
    }
    assert(filteredPayload.ok === true, "Expected ok true for filtered list.");
    assert(filteredPayload.filters.status === "completed", "Expected status filter to be reflected in payload.");
    assert(
      filteredPayload.result.value[0].status === "completed",
      `Expected server to use status filter, got ${filteredPayload.result.value[0].status}`,
    );
    assert(
      filteredPayload.result.value[0].sourceRefName === "refs/heads/feature/xyz",
      `Expected server to use sourceRefName filter, got ${filteredPayload.result.value[0].sourceRefName}`,
    );
    assert(
      filteredPayload.result.value[0].targetRefName === "refs/heads/release",
      `Expected server to use targetRefName filter, got ${filteredPayload.result.value[0].targetRefName}`,
    );

    passed = true;
    process.stdout.write("PASS azdo-pr-list smoke test\n");
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
  process.stderr.write(`FAIL azdo-pr-list smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
