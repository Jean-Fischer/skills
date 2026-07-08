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
  const root = await mkdtemp(join(tmpdir(), "azdo-vargroup-create-test-"));

  const server = createServer(async (req, res) => {
    const url = new URL(req.url || "", "http://127.0.0.1");

    if (req.method !== "POST" || !url.pathname.endsWith("/_apis/distributedtask/variablegroups")) {
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
        id: 20,
        name: payload.name,
        description: payload.description,
        type: payload.type,
        variables: payload.variables,
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
  const scriptPath = resolvePath(skillDir, "azdo-vargroup-create.mjs");

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

    const body = {
      name: "app-secrets",
      description: "Variables used by the deploy pipeline",
      type: "Vsts",
      variables: {
        apiUrl: { value: "https://example.local" },
      },
    };
    const bodyFile = join(root, "vargroup-body.json");
    await writeFile(bodyFile, JSON.stringify(body), "utf8");

    const result = await run(process.execPath, [scriptPath, "--body-file", bodyFile], { cwd: repoDir, env });
    assert(result.code === 0, `Expected exit code 0 for vargroup create, got ${result.code}. STDERR: ${result.stderr}`);
    let payload;
    try {
      payload = JSON.parse(result.stdout.trim());
    } catch (error) {
      throw new Error(
        `Failed to parse vargroup create payload as JSON: ${error?.message || String(result.stdout)}`,
      );
    }
    assert(payload.ok === true, "Expected ok true for vargroup create.");
    assert(payload.group.id === 20, `Expected group id 20, got ${payload.group.id}`);
    assert(payload.group.name === "app-secrets", `Expected group name app-secrets, got ${payload.group.name}`);

    passed = true;
    process.stdout.write("PASS azdo-vargroup-create smoke test\n");
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
  process.stderr.write(`FAIL azdo-vargroup-create smoke test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
