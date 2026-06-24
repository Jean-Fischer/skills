#!/usr/bin/env node
import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

function asString(value) {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function logInfo(msg) {
  process.stdout.write(`[cx-filtered-scan] ${msg}\n`);
}

function logError(msg) {
  process.stderr.write(`[cx-filtered-scan] ${msg}\n`);
}

function parseArgs(argv) {
  const args = {
    source: ".",
    outDir: "artifacts/checkmarx",
    projectName: "",
    branch: "",
    scanTypes: "sast,sca",
    outputName: "latest",
    keepWorkdir: false,
    debug: false,
  };

  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--source") args.source = argv[++i] ?? "";
    else if (arg === "--out-dir") args.outDir = argv[++i] ?? "";
    else if (arg === "--project-name") args.projectName = argv[++i] ?? "";
    else if (arg === "--branch") args.branch = argv[++i] ?? "";
    else if (arg === "--scan-types") args.scanTypes = argv[++i] ?? "";
    else if (arg === "--output-name") args.outputName = argv[++i] ?? "";
    else if (arg === "--keep-workdir") args.keepWorkdir = true;
    else if (arg === "--debug") args.debug = true;
    else if (arg.startsWith("-")) {
      logError(`Unknown option: ${arg}`);
      printUsage();
      process.exit(1);
    } else {
      rest.push(arg);
    }
  }

  if (!args.source) args.source = ".";
  if (!args.outDir) args.outDir = "artifacts/checkmarx";
  if (!args.scanTypes) args.scanTypes = "sast,sca";
  if (!args.outputName) args.outputName = "latest";

  return args;
}

function printUsage() {
  logInfo("Usage: node cx-filtered-scan.mjs [options]\n" +
    "  --source <dir>        Git repo root (default: .)\n" +
    "  --out-dir <dir>       Output directory for SARIF & JSON (default: artifacts/checkmarx)\n" +
    "  --project-name <name> Checkmarx project name (optional; inferred with security-gate rule)\n" +
    "  --branch <name>       Branch name (default: git rev-parse --abbrev-ref HEAD)\n" +
    "  --scan-types <list>   Scan types (default: sast,sca)\n" +
    "  --output-name <name>  SARIF base name (default: latest)\n" +
    "  --keep-workdir        Do not delete temporary filtered workdir on success\n" +
    "  --debug               Pass --debug to cx scan create\n");
}

async function runCommand(cmd, args, options = {}) {
  return new Promise((resolvePromise, rejectPromise) => {
    // Default to capturing stdout/stderr, but allow callers to override stdio
    const stdio = options.stdio ?? ["ignore", "pipe", "pipe"];
    const child = spawn(cmd, args, { ...options, stdio });

    let stdout = "";
    let stderr = "";

    // When stdio is "inherit", child.stdout/child.stderr will be null.
    // Guard the event handlers so we don't crash with "Cannot read properties of null (reading 'on')".
    if (child.stdout) {
      child.stdout.on("data", (d) => {
        stdout += d.toString();
      });
    }
    if (child.stderr) {
      child.stderr.on("data", (d) => {
        stderr += d.toString();
      });
    }

    child.on("error", (err) => {
      rejectPromise(err);
    });
    child.on("close", (code) => {
      resolvePromise({ code, stdout, stderr });
    });
  });
}

async function ensureGitRepo(sourceDir) {
  const result = await runCommand("git", ["-C", sourceDir, "rev-parse", "--is-inside-work-tree"]);
  if (result.code !== 0 || !result.stdout.trim()) {
    throw new Error(`Directory '${sourceDir}' is not a Git repository or git is not available.`);
  }
}

async function getGitBranch(sourceDir, explicitBranch) {
  if (explicitBranch && explicitBranch.trim()) return explicitBranch.trim();
  const result = await runCommand("git", ["-C", sourceDir, "rev-parse", "--abbrev-ref", "HEAD"]);
  if (result.code !== 0) {
    throw new Error(`Failed to determine Git branch from '${sourceDir}': ${result.stderr || result.stdout}`);
  }
  const branch = result.stdout.trim();
  if (!branch) throw new Error(`Git returned empty branch name for '${sourceDir}'.`);
  return branch;
}

async function getGitRemoteName(sourceDir) {
  const result = await runCommand("git", ["-C", sourceDir, "remote", "get-url", "origin"]);
  if (result.code !== 0) {
    throw new Error(`Failed to get git remote URL from '${sourceDir}': ${result.stderr || result.stdout}`);
  }
  const url = result.stdout.trim();
  if (!url) throw new Error("git remote get-url origin returned empty output.");
  const parts = url.split(/[\\/]+/);
  let last = parts[parts.length - 1];
  if (!last) throw new Error(`Cannot infer repository name from remote URL '${url}'.`);
  if (last.toLowerCase().endsWith(".git")) {
    last = last.slice(0, -4);
  }
  return last;
}

async function findSecurityGatePipeline(sourceDir) {
  const entries = await fs.readdir(sourceDir, { withFileTypes: true });
  const stack = entries.map((e) => ({ base: sourceDir, entry: e }));

  while (stack.length > 0) {
    const { base, entry } = stack.pop();
    const fullPath = join(base, entry.name);
    if (entry.isDirectory()) {
      // Skip .git directory to avoid unnecessary traversal
      if (entry.name === ".git") continue;
      const sub = await fs.readdir(fullPath, { withFileTypes: true });
      for (const e of sub) stack.push({ base: fullPath, entry: e });
    } else if (entry.isFile()) {
      if (entry.name === "security-gate.yml" || entry.name === "security-gate.yaml") {
        return fullPath;
      }
    }
  }

  return "";
}

async function resolveProjectName(sourceDir, explicitProjectName) {
  if (explicitProjectName && explicitProjectName.trim()) return explicitProjectName.trim();
  throw new Error("No project name provided. Please pass --project-name based on your pipeline and config.");
}

async function readBlacklistPatterns(sourceDir) {
  const blacklistPath = join(sourceDir, "cxblacklist.txt");
  try {
    const content = await fs.readFile(blacklistPath, "utf8");
    const lines = content.split(/\r?\n/);
    const patterns = [];
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      if (line.startsWith("#")) continue;
      patterns.push(line);
    }
    if (patterns.length === 0) {
      logInfo("cxblacklist.txt present but no usable patterns found.");
    } else {
      logInfo(`Loaded ${patterns.length} blacklist pattern(s) from cxblacklist.txt.`);
    }
    return patterns;
  } catch (err) {
    if (err && err.code === "ENOENT") {
      logInfo("No cxblacklist.txt found at repo root; proceeding without extra exclusions.");
      return [];
    }
    throw err;
  }
}

function normalizePath(path) {
  return path.split(/[\\/]+/).join("/");
}

function createWildcardRegex(pattern) {
  // Escape regex special chars except * and ?
  const escaped = pattern.replace(/[.+^${}()|\\]/g, "\\$&");
  const regexStr = "^" + escaped.replace(/\*/g, "[\\s\\S]*").replace(/\?/g, ".") + "$";
  return new RegExp(regexStr, "i");
}

function isBlacklistedPath(relPathNormalized, patterns) {
  if (!patterns || patterns.length === 0) return false;
  const rp = normalizePath(relPathNormalized);
  const name = rp.split("/").pop() || rp;

  for (const entry of patterns) {
    const e = entry;
    const hasWildcard = /[\*\?]/.test(e);
    if (hasWildcard) {
      if (e.length >= 3 && e.substring(0, 3) === "**/") {
        const tailPattern = e.substring(3);
        const nameRegex = createWildcardRegex(tailPattern);
        if (nameRegex.test(name)) return true;
        const fullRegex = createWildcardRegex(e);
        if (fullRegex.test(rp)) return true;
      } else {
        const fullRegex = createWildcardRegex(e);
        if (fullRegex.test(rp)) return true;
      }
    } else {
      if (rp.localeCompare(e, undefined, { sensitivity: "accent" }) === 0) return true;
    }
  }

  return false;
}

async function listGitFiles(sourceDir) {
  const result = await runCommand("git", ["-C", sourceDir, "ls-files"]);
  if (result.code !== 0) {
    throw new Error(`git ls-files failed for '${sourceDir}': ${result.stderr || result.stdout}`);
  }
  const files = result.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return files;
}

async function mkdirp(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

/**
 * Copy a file from src to dest, ensuring the destination directory exists.
 *
 * Returns true when the copy succeeds.
 * Returns false when the source file is missing (ENOENT) and logs a message.
 * All other errors are rethrown.
 */
async function copyFileWithDirs(src, dest) {
  const dir = dirname(dest);
  await mkdirp(dir);
  try {
    await fs.copyFile(src, dest);
    return true;
  } catch (err) {
    if (err && err.code === "ENOENT") {
      logInfo(`Source file missing, skipping: ${src}`);
      return false;
    }
    throw err;
  }
}

function makeTempWorkdir() {
  const base = tmpdir();
  const unique = `cxscan-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return resolve(base, unique);
}

async function buildFilteredWorkdir(sourceDir, patterns) {
  const workDir = makeTempWorkdir();
  await mkdirp(workDir);

  const allFiles = await listGitFiles(sourceDir);
  let copied = 0;
  let skipped = 0;

  for (const relPath of allFiles) {
    const relNorm = normalizePath(relPath);
    if (isBlacklistedPath(relNorm, patterns)) {
      skipped++;
      continue;
    }
    const srcFull = resolve(sourceDir, relPath.split("/").join(sep));
    const destFull = resolve(workDir, relPath.split("/").join(sep));
    const copiedOk = await copyFileWithDirs(srcFull, destFull);
    if (copiedOk) {
      copied++;
    } else {
      skipped++;
    }
  }

  logInfo(`Filtered workdir ready at '${workDir}': ${copied} file(s) copied, ${skipped} file(s) skipped (excluded or missing).`);
  return { workDir, copied, skipped };
}

async function runCxScan({ workDir, sourceDir, outDir, projectName, branch, scanTypes, outputName, debug }) {
  const outDirAbs = resolve(sourceDir, outDir);
  await mkdirp(outDirAbs);

  const args = [
    "scan",
    "create",
    "-s",
    workDir,
    "--project-name",
    projectName,
    "--branch",
    branch,
    "--report-format",
    "sarif",
    "--output-path",
    outDirAbs,
    "--output-name",
    outputName,
    "--scan-types",
    scanTypes,
  ];

  if (debug) args.push("--debug");

  logInfo(`Running: cx ${args.map((a) => (a.includes(" ") ? `"${a}"` : a)).join(" ")}`);

  const result = await runCommand("cx", args, { stdio: ["ignore", "inherit", "inherit"] });
  if (result.code !== 0) {
    throw new Error(`Checkmarx scan failed with exit code ${result.code}.`);
  }

  return { outDirAbs };
}

async function normalizeSarif({ sourceDir, outDir, outputName, projectName, cxCommand }) {
  const outDirAbs = resolve(sourceDir, outDir);
  const candidates = [
    resolve(outDirAbs, `${outputName}.sarif`),
    resolve(outDirAbs, `${outputName}.json`),
  ];

  let sarifPath = "";
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      sarifPath = candidate;
      break;
    } catch {
      // ignore
    }
  }

  if (!sarifPath) {
    throw new Error(`Could not find SARIF output for output-name '${outputName}' in '${outDirAbs}'.`);
  }

  const thisDir = dirname(fileURLToPath(import.meta.url));
  const normalizer = resolve(thisDir, "normalize-sarif.mjs");

  const cmdArgs = [normalizer, sarifPath, resolve(outDirAbs, "latest-findings.json"), projectName, cxCommand];
  logInfo(`Normalizing SARIF via: node ${cmdArgs.map((a) => (a.includes(" ") ? `"${a}"` : a)).join(" ")}`);

  const result = await runCommand(process.execPath, cmdArgs, { cwd: thisDir });
  if (result.code !== 0) {
    throw new Error(`SARIF normalization failed with exit code ${result.code}.`);
  }
}

async function removeDirRecursive(path) {
  try {
    await fs.rm(path, { recursive: true, force: true });
  } catch {
    // best effort
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sourceDir = resolve(args.source || ".");

  logInfo(`Source directory: ${sourceDir}`);
  await ensureGitRepo(sourceDir);

  const branch = await getGitBranch(sourceDir, args.branch);
  logInfo(`Using branch: ${branch}`);

  const projectName = await resolveProjectName(sourceDir, args.projectName);
  logInfo(`Using project name: ${projectName}`);

  const patterns = await readBlacklistPatterns(sourceDir);

  const { workDir } = await buildFilteredWorkdir(sourceDir, patterns);

  let scanOk = false;
  try {
    await runCxScan({
      workDir,
      sourceDir,
      outDir: args.outDir,
      projectName,
      branch,
      scanTypes: args.scanTypes,
      outputName: args.outputName,
      debug: args.debug,
    });
    scanOk = true;
  } catch (err) {
    logError(asString(err?.message || err));
    logError(`Filtered workdir preserved at '${workDir}' for inspection.`);
    process.exitCode = 1;
    return;
  }

  const cxCmdString = `cx scan create -s ${workDir} --project-name ${projectName} --branch ${branch} --report-format sarif --output-path ${resolve(
    sourceDir,
    args.outDir,
  )} --output-name ${args.outputName} --scan-types ${args.scanTypes}${args.debug ? " --debug" : ""}`;

  try {
    await normalizeSarif({
      sourceDir,
      outDir: args.outDir,
      outputName: args.outputName,
      projectName,
      cxCommand: cxCmdString,
    });
  } catch (err) {
    logError(asString(err?.message || err));
    logError(`Filtered workdir preserved at '${workDir}' for inspection.`);
    process.exitCode = 1;
    return;
  }

  if (!args.keepWorkdir && scanOk) {
    await removeDirRecursive(workDir);
    logInfo("Temporary filtered workdir removed.");
  } else {
    logInfo(`Temporary filtered workdir kept at '${workDir}'.`);
  }

  logInfo("Checkmarx scan and normalization completed successfully.");
}

main().catch((err) => {
  logError(asString(err?.stack || err));
  process.exit(1);
});
