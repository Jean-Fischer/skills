#!/usr/bin/env node
import { request as httpsRequest } from "node:https";
import { request as httpRequest } from "node:http";
import { URL } from "node:url";
import { resolveAzureDevOpsContext } from "./azdo-context.mjs";

function buildBasicAuthHeader(pat) {
  // Username portion is blank per handbook; value is ":PAT" base64-encoded.
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

async function main() {
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
  const apiUrl = new URL(`${context.collection}/_apis/projects?api-version=7.1`, baseUrl);

  const headers = {
    Authorization: buildBasicAuthHeader(pat.trim()),
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  try {
    const { statusCode } = await runRequest(apiUrl, headers);
    if (statusCode === 401 || statusCode === 403) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            authOk: false,
            reason: "unauthorized",
            statusCode,
            message:
              "Azure DevOps Server rejected the PAT (401/403). Verify AZDO_PAT and that it has rights to read projects.",
          },
        ) + "\n",
      );
      process.exit(3);
    }

    if (statusCode < 200 || statusCode >= 300) {
      process.stdout.write(
        JSON.stringify(
          {
            ok: false,
            authOk: false,
            reason: "unexpected-status",
            statusCode,
            message: `Azure DevOps Server returned unexpected status ${statusCode} when checking projects.`,
          },
        ) + "\n",
      );
      process.exit(4);
    }

    process.stdout.write(
      JSON.stringify(
        {
          ok: true,
          authOk: true,
          reason: null,
          statusCode,
          message: "PAT accepted by Azure DevOps Server.",
          context,
        },
      ) + "\n",
    );
    process.exit(0);
  } catch (error) {
    process.stdout.write(
      JSON.stringify(
        {
          ok: false,
          authOk: false,
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
// eslint-disable-next-line no-void
void main();
