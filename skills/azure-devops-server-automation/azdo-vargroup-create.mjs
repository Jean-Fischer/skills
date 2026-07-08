#!/usr/bin/env node
import { request as httpsRequest } from "node:https";
import { request as httpRequest } from "node:http";
import { URL } from "node:url";
import { readFile } from "node:fs/promises";
import { resolveAzureDevOpsContext } from "./azdo-context.mjs";

function buildBasicAuthHeader(pat) {
  const token = Buffer.from(`:${pat}`, "utf8").toString("base64");
  return `Basic ${token}`;
}

function runRequest(url, headers, body) {
  const client = url.protocol === "https:" ? httpsRequest : httpRequest;

  return new Promise((resolvePromise, rejectPromise) => {
    const req = client(url, { method: "POST", headers }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      res.on("end", () => {
        resolvePromise({
          statusCode: res.statusCode ?? 0,
          body: Buffer.concat(chunks).toString("utf8"),
        });
      });
    });

    req.on("error", (error) => {
      rejectPromise(error);
    });

    if (body) {
      req.write(body);
    }

    req.end();
  });
}

function parseArgs(argv) {
  const args = argv.slice(2);
  let bodyFile = null;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    const next = args[i + 1];

    if (arg === "--body-file" && next) {
      bodyFile = next;
      i += 1;
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write("Usage: azdo-vargroup-create.mjs --body-file <path-to-json>\n");
      process.exit(0);
    }
  }

  if (!bodyFile) {
    process.stderr.write("Missing required --body-file <path-to-json> argument.\n");
    process.exit(1);
  }

  return { bodyFile };
}

async function loadBody(bodyFile) {
  const text = await readFile(bodyFile, "utf8");
  JSON.parse(text);
  return text;
}

async function main() {
  const { bodyFile } = parseArgs(process.argv);

  const pat = process.env.AZDO_PAT;
  if (!pat || !pat.trim()) {
    process.stderr.write("AZDO_PAT is not set. Set AZDO_PAT to a Personal Access Token for Azure DevOps Server.\n");
    process.exit(1);
  }

  let context;
  try {
    context = await resolveAzureDevOpsContext();
  } catch (error) {
    process.stderr.write(`Failed to resolve Azure DevOps context: ${error?.message || String(error)}\n`);
    process.exit(2);
  }

  const baseUrl = new URL(context.baseUrl);
  const path = `_apis/distributedtask/variablegroups?api-version=7.1`;
  const apiUrl = new URL(path, baseUrl);

  let bodyJson;
  try {
    bodyJson = await loadBody(bodyFile);
  } catch (error) {
    process.stderr.write(`Failed to load body from ${bodyFile}: ${error?.message || String(error)}\n`);
    process.exit(3);
  }

  const headers = {
    Authorization: buildBasicAuthHeader(pat.trim()),
    "Content-Type": "application/json",
    Accept: "application/json",
    "Content-Length": Buffer.byteLength(bodyJson, "utf8"),
  };

  try {
    const { statusCode, body } = await runRequest(apiUrl, headers, bodyJson);

    if (statusCode < 200 || statusCode >= 300) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "unexpected-status",
            statusCode,
            message: `Azure DevOps Server returned unexpected status ${statusCode} when creating variable group.`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    let group;
    try {
      group = JSON.parse(body);
    } catch (error) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "invalid-json",
            statusCode,
            message: `Failed to parse variable group create response as JSON: ${error?.message || String(error)}`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    process.stdout.write(
      JSON.stringify(
        {
          ok: true,
          statusCode,
          context,
          group,
        },
      ) + "\n",
    );
    process.exit(0);
  } catch (error) {
    process.stdout.write(
      JSON.stringify(
        {
          ok: false,
          reason: "network-error",
          statusCode: 0,
          message: error?.message || String(error),
        },
      ) + "\n",
    );
    process.exit(5);
  }
}

// Execute immediately when run as a script.
void main();
