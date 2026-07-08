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
  const root = await mkdtemp(join(tmpdir(), "azdo-pipeline-get-test-"));

  const server = createServer((req, res) => {
    const url = new URL(req.url || "", "http://127.0.0.1");

    if (!url.pathname.includes("/_apis/pipelines")) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    if (url.pathname.endsWith("/pipelines/42")) {
      res.statusCode = 200;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ id: 42, name: "test-pipeline", revision: 1 }));
      return;
    }

    res.statusCode = 404;
    res.end("Pipeline not found");
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
  const scriptPath = resolvePath(skillDir, "azdo-pipeline-get.mjs");

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

    // Existing pipeline 42
    const okResult = await run(process.execPath, [scriptPath, "--id", "42"], { cwd: repoDir, env });
    assert(okResult.code === 0, `Expected exit code 0 for existing pipeline, got ${okResult.code}. STDERR: ${okResult.stderr}`);
    let okPayload;
    try {
      okPayload = JSON.parse(okResult.stdout.trim());
    } catch (error) {
      throw new Error(`Failed to parse pipeline payload as JSON: ${error?.message || String(error)}\n${okResult.stdout}`);
    }
    assert(okPayload.ok === true, "Expected ok true for existing pipeline.");
    assert(okPayload.pipeline.id === 42, `Expected pipeline id 42, got ${okPayload.pipeline.id}`);

    // Missing pipeline 99
    const notFoundResult = await run(process.execPath, [scriptPath, "--id", "99"], { cwd: repoDir, env });
    assert(
      notFoundResult.code === 4,
      `Expected exit code 4 for missing pipeline, got ${notFoundResult.code}. STDERR: ${notFoundResult.stderr}`,
    );
    let notFoundPayload;
    try {
      notFoundPayload = JSON.parse(notFoundResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse not-found payload as JSON: ${error?.message || String(error)}\n${notFoundResult.stdout}`,
      );
    }
    assert(notFoundPayload.ok === false, "Expected ok false for missing pipeline.");
    assert(notFoundPayload.reason === "not-found", `Expected reason "not-found", got ${notFoundPayload.reason}`);
    assert(notFoundPayload.statusCode === 404, `Expected statusCode 404 for missing pipeline, got ${notFoundPayload.statusCode}`);

    passed = true;
    process.stdout.write("PASS azdo-pipeline-get smoke test\n");
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
  process.stderr.write(`FAIL azdo-pipeline-get smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
