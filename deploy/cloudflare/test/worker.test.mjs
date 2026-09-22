import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

import {
  base64urlDecode,
  base64urlEncode,
  brokerGrant,
  manifestFor,
  normalizeWebhook,
  setupTokenIsValid,
} from "../src/index.mjs";

test("setup token expires after one hour", () => {
  const token = "v1.1000.random-secret";
  assert.equal(setupTokenIsValid(token, token, 1000), true);
  assert.equal(setupTokenIsValid(token, token, 4600), true);
  assert.equal(setupTokenIsValid(token, token, 4601), false);
  assert.equal(setupTokenIsValid(token, "v1.1000.other", 1000), false);
});

test("manifest preserves minimum GitHub App permissions", () => {
  const manifest = manifestFor("https://cwb.example.workers.dev");
  assert.deepEqual(manifest.default_permissions, {
    checks: "write",
    contents: "read",
    pull_requests: "read",
  });
  assert.deepEqual(manifest.default_events, ["pull_request", "push"]);
  assert.equal(
    manifest.hook_attributes.url,
    "https://cwb.example.workers.dev/webhooks/github",
  );
  assert.equal(
    manifest.redirect_url,
    "https://cwb.example.workers.dev/setup/github/callback",
  );
  assert.equal(manifest.public, false);
});

test("push event normalizes to a queue target", () => {
  const decision = normalizeWebhook("push", {
    after: "a".repeat(40),
    ref: "refs/heads/main",
    repository: { full_name: "octo/demo", private: false },
    installation: { id: 1234 },
  });
  assert.equal(decision.disposition, "scan");
  assert.equal(decision.target.repository, "octo/demo");
  assert.equal(decision.target.installation_id, 1234);
  assert.equal(decision.target.head_sha, "a".repeat(40));
});

test("unsupported pull request action is ignored", () => {
  const decision = normalizeWebhook("pull_request", {
    action: "closed",
    number: 42,
    repository: { full_name: "octo/demo", private: false },
    installation: { id: 1234 },
    pull_request: { head: { sha: "a".repeat(40) } },
  });
  assert.equal(decision.disposition, "ignored");
});

test("base64url helper round trips UTF-8 bytes", () => {
  const source = new TextEncoder().encode("CWB free deployment");
  const encoded = base64urlEncode(source);
  assert.deepEqual(base64urlDecode(encoded), source);
});


test("private repository webhook is rejected before queueing", () => {
  const decision = normalizeWebhook("push", {
    after: "a".repeat(40),
    ref: "refs/heads/main",
    repository: { full_name: "octo/private-demo", private: true },
    installation: { id: 1234 },
  });
  assert.equal(decision.disposition, "private-unsupported");
  assert.equal(decision.target, undefined);
});

test("broker grant is deterministic and delivery-bound", async () => {
  const target = {
    event: "push",
    repository: "octo/demo",
    head_sha: "a".repeat(40),
    installation_id: 1234,
    action: null,
    pull_request_number: null,
    merge_commit_sha: null,
    ref: "refs/heads/main",
  };
  const first = await brokerGrant(
    "webhook-secret",
    "delivery-123",
    target,
  );
  const same = await brokerGrant(
    "webhook-secret",
    "delivery-123",
    target,
  );
  const changed = await brokerGrant(
    "webhook-secret",
    "delivery-123",
    { ...target, head_sha: "b".repeat(40) },
  );

  assert.equal(first, same);
  assert.notEqual(first, changed);
  assert.match(first, /^[0-9a-f]{64}$/);
});
