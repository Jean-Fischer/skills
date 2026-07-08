#!/usr/bin/env node
import { createServer } from "node:http";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
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
  const root = await mkdtemp(join(tmpdir(), "azdo-pipeline-run-test-"));

  const server = createServer(async (req, res) => {
    const url = new URL(req.url || "", "http://127.0.0.1");

    if (req.method !== "POST") {
      res.statusCode = 405;
      res.end("Method not allowed");
      return;
    }

    if (!url.pathname.includes("/_apis/pipelines") || !url.pathname.endsWith("/runs")) {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    const chunks = [];
    for await (const chunk of req) {
      chunks.push(Buffer.from(chunk));
    }
    const bodyText = Buffer.concat(chunks).toString("utf8");

    let payload;
    try {
      payload = JSON.parse(bodyText || "{}");
    } catch (error) {
      res.statusCode = 400;
      res.end("Invalid JSON");
      return;
    }

    res.statusCode = 201;
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        id: 100,
        state: "inProgress",
        requestBody: payload,
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
  const scriptPath = resolvePath(skillDir, "azdo-pipeline-run.mjs");

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

    // Case 1: default body ({})
    const defaultResult = await run(process.execPath, [scriptPath, "--id", "7"], { cwd: repoDir, env });
    assert(
      defaultResult.code === 0,
      `Expected exit code 0 for default run, got ${defaultResult.code}. STDERR: ${defaultResult.stderr}`,
    );
    let defaultPayload;
    try {
      defaultPayload = JSON.parse(defaultResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse default run payload as JSON: ${error?.message || String(error)}\n${defaultResult.stdout}`,
      );
    }
    assert(defaultPayload.ok === true, "Expected ok true for default run.");
    assert(defaultPayload.run.id === 100, `Expected run id 100, got ${defaultPayload.run.id}`);

    // Case 2: custom body-file
    const customBody = {
      templateParameters: { environment: "qa" },
      variables: {
        buildConfiguration: { value: "Release" },
      },
    };
    const bodyFile = join(root, "run-body.json");
    await writeFile(bodyFile, JSON.stringify(customBody), "utf8");

    const customResult = await run(
      process.execPath,
      [scriptPath, "--id", "7", "--body-file", bodyFile],
      { cwd: repoDir, env },
    );
    assert(
      customResult.code === 0,
      `Expected exit code 0 for custom run, got ${customResult.code}. STDERR: ${customResult.stderr}`,
    );
    let customPayload;
    try {
      customPayload = JSON.parse(customResult.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse custom run payload as JSON: ${error?.message || String(error)}\n${customResult.stdout}`,
      );
    }
    assert(customPayload.ok === true, "Expected ok true for custom run.");
    assert(
      customPayload.run.requestBody.templateParameters.environment === "qa",
      "Expected custom run body-file to be forwarded to server.",
    );

    passed = true;
    process.stdout.write("PASS azdo-pipeline-run smoke test\n");
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
  process.stderr.write(`FAIL azdo-pipeline-run smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
