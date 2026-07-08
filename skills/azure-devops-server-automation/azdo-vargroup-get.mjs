#!/usr/bin/env node
import { request as httpsRequest } from "node:https";
import { request as httpRequest } from "node:http";
import { URL } from "node:url";
import { resolveAzureDevOpsContext } from "./azdo-context.mjs";

function buildBasicAuthHeader(pat) {
  const token = Buffer.from(`:${pat}`, "utf8").toString("base64");
  return `Basic ${token}`;
}

function runRequest(url, headers) {
  const client = url.protocol === "https:" ? httpsRequest : httpRequest;

  return new Promise((resolvePromise, rejectPromise) => {
    const req = client(url, { method: "GET", headers }, (res) => {
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

    req.end();
  });
}

function parseArgs(argv) {
  const args = argv.slice(2);
  let name = null;
  let id = null;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    const next = args[i + 1];

    if ((arg === "--name" || arg === "-n") && next) {
      name = next;
      i += 1;
    } else if ((arg === "--id" || arg === "-i") && next) {
      id = next;
      i += 1;
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write("Usage: azdo-vargroup-get.mjs [--name <groupName>] [--id <groupId>]\n");
      process.exit(0);
    }
  }

  if (!name && !id) {
    process.stderr.write("Specify either --name <groupName> or --id <groupId>.\n");
    process.exit(1);
  }

  return { groupName: name, groupId: id };
}

function buildQuery(groupName, groupId) {
  const params = new URLSearchParams();
  params.set("api-version", "7.1");

  if (groupName) {
    params.set("groupName", groupName);
  }
  if (groupId) {
    params.set("groupIds", groupId);
  }

  return params.toString();
}

async function main() {
  const { groupName, groupId } = parseArgs(process.argv);

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
  const query = buildQuery(groupName, groupId);
  const path = `${context.collection}/${context.project}/_apis/distributedtask/variablegroups?${query}`;
  const apiUrl = new URL(path, baseUrl);

  const headers = {
    Authorization: buildBasicAuthHeader(pat.trim()),
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  try {
    const { statusCode, body } = await runRequest(apiUrl, headers);

    if (statusCode < 200 || statusCode >= 300) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "unexpected-status",
            statusCode,
            message: `Azure DevOps Server returned unexpected status ${statusCode} when reading variable group.`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    let result;
    try {
      result = JSON.parse(body);
    } catch (error) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "invalid-json",
            statusCode,
            message: `Failed to parse variable group response as JSON: ${error?.message || String(error)}`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    const first = Array.isArray(result.value) && result.value.length > 0 ? result.value[0] : null;
    if (!first) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "not-found",
            statusCode,
            message: "No matching variable group found.",
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
          group: first,
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
