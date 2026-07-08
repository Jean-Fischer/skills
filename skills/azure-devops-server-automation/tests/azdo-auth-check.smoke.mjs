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
  const root = await mkdtemp(join(tmpdir(), "azdo-auth-check-test-"));

  let mode = "ok"; // ok | unauthorized | error

  const server = createServer((req, res) => {
    if (!req.url?.includes("/_apis/projects")) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    if (mode === "unauthorized") {
      res.statusCode = 401;
      res.end("Unauthorized");
      return;
    }

    if (mode === "error") {
      res.statusCode = 500;
      res.end("Server error");
      return;
    }

    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ count: 1, value: [{ name: "TestProject" }] }));
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

  return { root, server, baseUrl, getMode: () => mode, setMode: (m) => { mode = m; } };
}

async function main() {
  const thisDir = dirname(fileURLToPath(import.meta.url));
  const skillDir = resolvePath(thisDir, "..");
  const scriptPath = resolvePath(skillDir, "azdo-auth-check.mjs");

  const { root, server, baseUrl, setMode } = await setupFakeServer();
  let passed = false;

  try {
    // We control context resolution via overrides. azdo-auth-check currently
    // calls resolveAzureDevOpsContext() with no arguments, so we point
    // process.cwd at a repo directory and ensure azdo-context derives
    // baseUrl/collection/project/repository from a remote that uses our
    // fake server URL.

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

    // Case 1: 200 OK → authOk: true
    setMode("ok");
    const okResult = await run(process.execPath, [scriptPath], { cwd: repoDir, env });
    assert(okResult.code === 0, `Expected exit code 0 for OK mode, got ${okResult.code}. STDERR: ${okResult.stderr}`);
    let okPayload;
    try {
      okPayload = JSON.parse(okResult.stdout.trim());
    } catch (error) {
      throw new Error(`Failed to parse OK payload as JSON: ${error?.message || String(error)}\n${okResult.stdout}`);
    }
    assert(okPayload.authOk === true, "Expected authOk true for OK mode.");
    assert(okPayload.statusCode === 200, `Expected statusCode 200 for OK mode, got ${okPayload.statusCode}`);

    // Case 2: 401 Unauthorized → authOk: false, reason: "unauthorized"
    setMode("unauthorized");
    const unauthorizedResult = await run(process.execPath, [scriptPath], { cwd: repoDir, env });
    assert(
      unauthorizedResult.code === 3,
      `Expected exit code 3 for unauthorized mode, got ${unauthorizedResult.code}. STDERR: ${unauthorizedResult.stderr}`,
    );
    let unauthorizedPayload;
    try {
      unauthorizedPayload = JSON.parse(unauthorizedResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse unauthorized payload as JSON: ${error?.message || String(error)}\n${unauthorizedResult.stdout}`,
      );
    }
    assert(unauthorizedPayload.authOk === false, "Expected authOk false for unauthorized mode.");
    assert(unauthorizedPayload.reason === "unauthorized", `Expected reason "unauthorized", got ${unauthorizedPayload.reason}`);
    assert(
      unauthorizedPayload.statusCode === 401,
      `Expected statusCode 401 for unauthorized mode, got ${unauthorizedPayload.statusCode}`,
    );

    // Case 3: 500 error → authOk: false, reason: "unexpected-status"
    setMode("error");
    const errorResult = await run(process.execPath, [scriptPath], { cwd: repoDir, env });
    assert(
      errorResult.code === 4,
      `Expected exit code 4 for error mode, got ${errorResult.code}. STDERR: ${errorResult.stderr}`,
    );
    let errorPayload;
    try {
      errorPayload = JSON.parse(errorResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse error payload as JSON: ${error?.message || String(error)}\n${errorResult.stdout}`,
      );
    }
    assert(errorPayload.authOk === false, "Expected authOk false for error mode.");
    assert(
      errorPayload.reason === "unexpected-status",
      `Expected reason "unexpected-status", got ${errorPayload.reason}`,
    );
    assert(errorPayload.statusCode === 500, `Expected statusCode 500 for error mode, got ${errorPayload.statusCode}`);

    passed = true;
    process.stdout.write("PASS azdo-auth-check smoke test\n");
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
  process.stderr.write(`FAIL azdo-auth-check smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
