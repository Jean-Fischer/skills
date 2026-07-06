#!/usr/bin/env node
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const thisDir = dirname(fileURLToPath(import.meta.url));
const skillDir = resolve(thisDir, "..");
const scriptPath = resolve(skillDir, "cx-filtered-scan.mjs");

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

async function setupRepo() {
  const root = await mkdtemp(join(tmpdir(), "cx-filtered-scan-test-"));
  const repoDir = join(root, "repo");
  const binDir = join(root, "bin");
  await mkdir(repoDir, { recursive: true });
  await mkdir(binDir, { recursive: true });

  await run("git", ["init"], { cwd: repoDir });
  await run("git", ["config", "user.email", "test@example.com"], { cwd: repoDir });
  await run("git", ["config", "user.name", "Test Runner"], { cwd: repoDir });
  await run("git", ["checkout", "-b", "test-branch"], { cwd: repoDir });
  await run("git", ["remote", "add", "origin", "https://example.test/org/demo-repo.git"], { cwd: repoDir });

  return { root, repoDir, binDir };
}

async function createFakeCx(binDir) {
  const fakeCxPath = join(binDir, "fake-cx.mjs");
  const fakeCx = `#!/usr/bin/env node
import { mkdir, readdir, writeFile } from "node:fs/promises";
import { join, resolve, relative } from "node:path";

async function walk(dir, root = dir, acc = []) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      await walk(full, root, acc);
    } else {
      acc.push(relative(root, full).split("\\\\").join("/"));
    }
  }
  return acc.sort();
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] !== "scan" || args[1] !== "create") {
    console.error("Unexpected cx invocation: " + args.join(" "));
    process.exit(2);
  }

  const sourceIndex = args.indexOf("-s");
  const outputPathIndex = args.indexOf("--output-path");
  const outputNameIndex = args.indexOf("--output-name");
  const sourceDir = resolve(args[sourceIndex + 1]);
  const outputDir = resolve(args[outputPathIndex + 1]);
  const outputName = args[outputNameIndex + 1];

  const files = await walk(sourceDir);
  const weirdFile = files.find((file) => file.includes("\\n")) || files.find((file) => /odd name\.txt$/i.test(file)) || files[0] || "included.txt";
  await mkdir(outputDir, { recursive: true });
  await writeFile(join(outputDir, "fake-cx-files.json"), JSON.stringify(files, null, 2) + "\\n", "utf8");

  const sarif = {
    version: "2.1.0",
    runs: [
      {
        tool: {
          driver: {
            name: "fake-cx",
            rules: [
              {
                id: "CX-TEST-1",
                shortDescription: { text: "Critical test finding" },
                properties: { "security-severity": "9.5" },
                helpUri: "https://example.test/rule"
              }
            ]
          }
        },
        results: [
          {
            ruleId: "CX-TEST-1",
            message: { text: "Test critical finding" },
            locations: [
              {
                physicalLocation: {
                  artifactLocation: { uri: weirdFile },
                  region: { startLine: 1, endLine: 1 }
                }
              }
            ]
          }
        ]
      }
    ]
  };

  await writeFile(join(outputDir, outputName + ".sarif"), JSON.stringify(sarif, null, 2) + "\\n", "utf8");
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exit(1);
});
`;

  await writeFile(fakeCxPath, fakeCx, { encoding: "utf8" });
  return fakeCxPath;
}

async function writeRepoFixture(repoDir) {
  const weirdName = process.platform === "win32" ? "odd name.txt" : "odd\nname.txt";
  await writeFile(join(repoDir, "included.txt"), "keep me\n", "utf8");
  await writeFile(join(repoDir, weirdName), "weird but tracked\n", "utf8");
  await writeFile(join(repoDir, "skip.tmp"), "exclude me\n", "utf8");
  await writeFile(join(repoDir, "cxblacklist.txt"), "skip.tmp\n", "utf8");

  await run("git", ["add", "."], { cwd: repoDir });
  const commit = await run("git", ["commit", "-m", "test fixture"], { cwd: repoDir });
  assert(commit.code === 0, `Failed to commit fixture: ${commit.stderr || commit.stdout}`);
  return {
    weirdName,
    regressionMode: process.platform === "win32" ? "space-only" : "newline",
  };
}

async function runSubject(repoDir, fakeCxPath) {
  const env = {
    ...process.env,
    CX_BIN: process.execPath,
    CX_BIN_ARGS: JSON.stringify([fakeCxPath]),
  };

  return run(process.execPath, [
    scriptPath,
    "--source", repoDir,
    "--out-dir", "artifacts/checkmarx",
    "--project-name", "test-project",
    "--branch", "test-branch",
    "--output-name", "latest",
  ], { cwd: repoDir, env });
}

function verifySyntheticNullParsing() {
  const gitOutput = `included.txt\0odd\nname.txt\0skip.tmp\0`;
  const parsedWithNull = gitOutput.split("\0").filter(Boolean);
  const parsedWithNewline = gitOutput.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);

  assert(parsedWithNull.includes("odd\nname.txt"), "Expected NUL-delimited parsing to preserve newline-containing filenames.");
  assert(!parsedWithNewline.includes("odd\nname.txt"), "Expected newline-delimited parsing to lose newline-containing filenames.");
}

async function verifyOutputs(repoDir, weirdName, regressionMode) {
  const outDir = join(repoDir, "artifacts", "checkmarx");
  const fakeFiles = JSON.parse(await readFile(join(outDir, "fake-cx-files.json"), "utf8"));
  const normalized = JSON.parse(await readFile(join(outDir, "latest-findings.json"), "utf8"));

  assert(fakeFiles.includes("included.txt"), "Expected included.txt to be present in fake cx scan input.");
  assert(
    fakeFiles.includes(weirdName),
    regressionMode === "newline"
      ? "Expected newline-containing tracked filename to be preserved in fake cx scan input."
      : "Expected unusual tracked filename to be preserved in fake cx scan input.",
  );
  assert(!fakeFiles.includes("skip.tmp"), "Expected blacklisted file skip.tmp to be excluded from fake cx scan input.");

  assert(normalized.status === "findings", `Expected normalized artifact status to be findings, got ${normalized.status}`);
  assert(normalized.summary.critical === 1, `Expected one critical finding, got ${normalized.summary.critical}`);
  assert(Array.isArray(normalized.findings) && normalized.findings.length === 1, "Expected one normalized finding.");
  assert(normalized.findings[0].filePath === weirdName, `Expected normalized finding path to be ${JSON.stringify(weirdName)}, got ${JSON.stringify(normalized.findings[0].filePath)}`);
}

async function main() {
  const { root, repoDir, binDir } = await setupRepo();
  let passed = false;
  try {
    const fakeCxPath = await createFakeCx(binDir);
    verifySyntheticNullParsing();
    const { weirdName, regressionMode } = await writeRepoFixture(repoDir);

    const result = await runSubject(repoDir, fakeCxPath);
    assert(result.code === 0, `cx-filtered-scan.mjs failed.\nSTDOUT:\n${result.stdout}\nSTDERR:\n${result.stderr}`);

    await verifyOutputs(repoDir, weirdName, regressionMode);
    passed = true;
    process.stdout.write(`PASS cx-filtered-scan smoke/regression test (${regressionMode})\n`);
  } finally {
    if (passed) {
      await rm(root, { recursive: true, force: true });
    } else {
      process.stderr.write(`Preserved temp test root for inspection: ${root}\n`);
    }
  }
}

main().catch((error) => {
  process.stderr.write(`FAIL cx-filtered-scan smoke/regression test\n${error?.stack || String(error)}\n`);
  process.exit(1);
});
