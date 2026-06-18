#!/usr/bin/env node
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

function asString(value) {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function toSeverity(value) {
  const text = asString(value).toLowerCase();
  if (!text) return "";
  if (text.includes("critical")) return "critical";
  if (text.includes("high")) return "high";
  if (text === "error") return "high";
  return "";
}

function severityFromScore(value) {
  const score = Number(value);
  if (!Number.isFinite(score)) return "";
  if (score >= 9) return "critical";
  if (score >= 7) return "high";
  return "";
}

function getNestedStrings(value, seen = new Set()) {
  if (!value || typeof value !== "object" || seen.has(value)) return [];
  seen.add(value);
  const out = [];
  if (Array.isArray(value)) {
    for (const item of value) out.push(...getNestedStrings(item, seen));
    return out;
  }
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === "string") out.push({ key, value: entry });
    else if (entry && typeof entry === "object") out.push(...getNestedStrings(entry, seen));
  }
  return out;
}

function getRuleMap(sarif) {
  const map = new Map();
  for (const run of sarif?.runs ?? []) {
    for (const rule of run?.tool?.driver?.rules ?? []) {
      if (rule?.id) map.set(rule.id, rule);
    }
  }
  return map;
}

function getLocation(result) {
  const loc = result?.locations?.[0]?.physicalLocation;
  const artifact = loc?.artifactLocation ?? {};
  const region = loc?.region ?? {};
  const uri = asString(artifact.uri || artifact.uriBaseId || artifact.index);
  return {
    filePath: uri.replace(/^file:\/\//i, "").replace(/^\/+/, ""),
    startLine: Number(region.startLine) || undefined,
    endLine: Number(region.endLine) || Number(region.startLine) || undefined,
    snippet: asString(region.snippet?.text).trim() || undefined,
  };
}

function getMessage(result) {
  return asString(result?.message?.text || result?.message?.markdown || result?.shortDescription?.text).trim();
}

function getSeverity(result, rule) {
  const candidates = [
    result?.properties?.["security-severity"],
    rule?.properties?.["security-severity"],
    result?.properties?.severity,
    result?.properties?.severityLevel,
    result?.properties?.priority,
    result?.properties?.risk,
    rule?.properties?.severity,
    rule?.properties?.securitySeverity,
    rule?.properties?.["security-severity"],
    rule?.defaultConfiguration?.level,
    result?.level,
  ];
  for (const candidate of candidates) {
    const severityFromSecurityScore = severityFromScore(candidate);
    if (severityFromSecurityScore) return severityFromSecurityScore;
    const severity = toSeverity(candidate);
    if (severity) return severity;
  }
  const strings = [
    ...getNestedStrings(result?.properties),
    ...getNestedStrings(rule?.properties),
  ];
  for (const entry of strings) {
    const severity = toSeverity(entry.value);
    if (severity) return severity;
  }
  return "";
}

function normalize(sarif, meta) {
  const errors = [];
  const findings = [];
  const ruleMap = getRuleMap(sarif);

  for (const run of sarif?.runs ?? []) {
    for (const result of run?.results ?? []) {
      try {
        const rule = ruleMap.get(result?.ruleId);
        const severity = getSeverity(result, rule);
        if (severity !== "critical" && severity !== "high") continue;
        const location = getLocation(result);
        findings.push({
          severity,
          ruleId: asString(result?.ruleId || rule?.id),
          message: getMessage(result),
          filePath: location.filePath,
          startLine: location.startLine,
          endLine: location.endLine,
          helpUri: asString(result?.helpUri || rule?.helpUri) || undefined,
          snippet: location.snippet,
        });
      } catch (error) {
        errors.push(asString(error?.message || error));
      }
    }
  }

  findings.sort((a, b) => {
    const severityRank = { critical: 0, high: 1 };
    const sr = (severityRank[a.severity] ?? 9) - (severityRank[b.severity] ?? 9);
    if (sr !== 0) return sr;
    const fp = a.filePath.localeCompare(b.filePath);
    if (fp !== 0) return fp;
    const line = (a.startLine ?? 0) - (b.startLine ?? 0);
    if (line !== 0) return line;
    return a.ruleId.localeCompare(b.ruleId);
  });

  return {
    status: errors.length > 0 ? (findings.length > 0 ? "partial" : "failed") : findings.length > 0 ? "findings" : "clean",
    generatedAt: new Date().toISOString(),
    projectName: meta.projectName || "",
    command: meta.command || "",
    summary: {
      critical: findings.filter((finding) => finding.severity === "critical").length,
      high: findings.filter((finding) => finding.severity === "high").length,
      total: findings.length,
    },
    findings,
    errors,
  };
}

async function main() {
  const [inputPath, outputPath, projectName = "", command = ""] = process.argv.slice(2);
  if (!inputPath || !outputPath) {
    console.error("Usage: node normalize-sarif.mjs <input.sarif.json> <output.json> [projectName] [command]");
    process.exit(1);
  }

  const resolvedInput = resolve(inputPath);
  const resolvedOutput = resolve(outputPath);
  const meta = { projectName, command };

  let sarif;
  try {
    sarif = JSON.parse(await readFile(resolvedInput, "utf8"));
  } catch (error) {
    const artifact = {
      status: "failed",
      generatedAt: new Date().toISOString(),
      projectName,
      command,
      summary: { critical: 0, high: 0, total: 0 },
      findings: [],
      errors: [asString(error?.message || error)],
    };
    await mkdir(dirname(resolvedOutput), { recursive: true });
    await writeFile(resolvedOutput, JSON.stringify(artifact, null, 2) + "\n", "utf8");
    process.exit(1);
  }

  const artifact = normalize(sarif, meta);
  await mkdir(dirname(resolvedOutput), { recursive: true });
  await writeFile(resolvedOutput, JSON.stringify(artifact, null, 2) + "\n", "utf8");

  if (artifact.status === "failed") process.exit(1);
  if (artifact.status === "partial") process.exitCode = 1;
}

main().catch((error) => {
  console.error(asString(error?.stack || error));
  process.exit(1);
});
