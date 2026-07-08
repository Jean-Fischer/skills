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
  const root = await mkdtemp(join(tmpdir(), "azdo-vargroup-list-test-"));

  const server = createServer((req, res) => {
    const url = new URL(req.url || "", "http://127.0.0.1");

    if (!url.pathname.includes("/_apis/distributedtask/variablegroups")) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    const groupName = url.searchParams.get("groupName") || "app-secrets";

    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        count: 1,
        value: [
          {
            id: 10,
            name: groupName,
            description: "Variables used by the deploy pipeline",
            type: "Vsts",
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
  const scriptPath = resolvePath(skillDir, "azdo-vargroup-list.mjs");

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

    const result = await run(process.execPath, [scriptPath, "--name", "app-secrets"], { cwd: repoDir, env });
    assert(result.code === 0, `Expected exit code 0 for vargroup list, got ${result.code}. STDERR: ${result.stderr}`);
    let payload;
    try {
      payload = JSON.parse(result.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse vargroup list payload as JSON: ${error?.message || String(error)}\n${result.stdout}`,
      );
    }
    assert(payload.ok === true, "Expected ok true for vargroup list.");
    assert(payload.result.count === 1, `Expected count 1, got ${payload.result.count}`);
    assert(payload.result.value[0].name === "app-secrets", `Expected group name app-secrets, got ${payload.result.value[0].name}`);

    passed = true;
    process.stdout.write("PASS azdo-vargroup-list smoke test\n");
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
  process.stderr.write(`FAIL azdo-vargroup-list smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
