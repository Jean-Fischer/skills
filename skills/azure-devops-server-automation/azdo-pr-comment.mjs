#!/usr/bin/env node
import { request as httpsRequest } from "node:https";
import { request as httpRequest } from "node:http";
import { URL } from "node:url";
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
  let id = null;
  let message = null;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    const next = args[i + 1];

    if ((arg === "--id" || arg === "-i") && next) {
      id = next;
      i += 1;
    } else if ((arg === "--message" || arg === "-m") && next) {
      message = next;
      i += 1;
    } else if (arg === "--help" || arg === "-h") {
      process.stdout.write("Usage: azdo-pr-comment.mjs --id <pullRequestId> --message <text>\n");
      process.exit(0);
    }
  }

  if (!id) {
    process.stderr.write("Missing required --id <pullRequestId> argument.\n");
    process.exit(1);
  }

  if (!message) {
    process.stderr.write("Missing required --message <text> argument.\n");
    process.exit(1);
  }

  const numericId = Number(id);
  if (!Number.isInteger(numericId) || numericId <= 0) {
    process.stderr.write("pullRequestId must be a positive integer.\n");
    process.exit(1);
  }

  return { pullRequestId: numericId, message };
}

async function main() {
  const { pullRequestId, message } = parseArgs(process.argv);

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
  const path = `${context.collection}/${context.project}/_apis/git/repositories/${encodeURIComponent(
    context.repository,
  )}/pullRequests/${pullRequestId}/threads?api-version=7.1`;
  const apiUrl = new URL(path, baseUrl);

  const bodyObject = {
    comments: [
      {
        parentCommentId: 0,
        content: message,
        commentType: 1,
      },
    ],
    status: 1,
  };

  const bodyJson = JSON.stringify(bodyObject);

  const headers = {
    Authorization: buildBasicAuthHeader(pat.trim()),
    "Content-Type": "application/json",
    Accept: "application/json",
    "Content-Length": Buffer.byteLength(bodyJson, "utf8"),
  };

  try {
    const { statusCode, body } = await runRequest(apiUrl, headers, bodyJson);

    if (statusCode === 404) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "not-found",
            statusCode,
            message: `Pull request ${pullRequestId} was not found when creating comment thread.`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    if (statusCode < 200 || statusCode >= 300) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "unexpected-status",
            statusCode,
            message: `Azure DevOps Server returned unexpected status ${statusCode} when creating comment thread for pull request ${pullRequestId}.`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    let thread;
    try {
      thread = JSON.parse(body);
    } catch (error) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            reason: "invalid-json",
            statusCode,
            message: `Failed to parse comment thread response as JSON: ${error?.message || String(error)}`,
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
          pullRequestId,
          thread,
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
