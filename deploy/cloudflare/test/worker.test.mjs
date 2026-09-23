import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

if (!globalThis.crypto) globalThis.crypto = webcrypto;

import worker, {
  base64urlDecode,
  base64urlEncode,
  brokerGrant,
  buildManifestState,
  buildMarketplaceOAuthState,
  deactivateMarketplaceInstallation,
  manifestFor,
  marketplaceAccountKey,
  normalizeMarketplacePurchase,
  normalizeWebhook,
  parseMarketplaceOAuthState,
  setupTokenIsValid,
  validateQueuedTokenEndpoint,
  verifyManifestState,
  verifyMarketplaceOAuthState,
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


test("queued token endpoint is restricted to workers.dev broker path", () => {
  assert.equal(
    validateQueuedTokenEndpoint(
      "https://cwb-github-free.kohli217.workers.dev/tokens/github",
    ),
    "https://cwb-github-free.kohli217.workers.dev/tokens/github",
  );

  for (const value of [
    "http://cwb-github-free.kohli217.workers.dev/tokens/github",
    "https://example.com/tokens/github",
    "https://cwb-github-free.kohli217.workers.dev/other",
    "https://cwb-github-free.kohli217.workers.dev/tokens/github?next=evil",
  ]) {
    assert.throws(() => validateQueuedTokenEndpoint(value));
  }
});


test("manifest state is signed, time-bounded, and tamper-evident", async () => {
  const secret = "v1.1000.setup-secret";
  const state = await buildManifestState(secret, 1000);

  assert.equal(await verifyManifestState(secret, state, 1000), true);
  assert.equal(await verifyManifestState(secret, state, 4600), true);
  assert.equal(await verifyManifestState(secret, state, 4601), false);

  const parts = state.split(".");
  const tampered = [parts[0], parts[1], "different-nonce", parts[3]].join(".");
  assert.equal(await verifyManifestState(secret, tampered, 1000), false);
  assert.equal(
    await verifyManifestState("v1.1000.other-secret", state, 1000),
    false,
  );
});

test("manifest state rejects malformed and far-future values", async () => {
  const secret = "v1.1000.setup-secret";

  assert.equal(await verifyManifestState(secret, "", 1000), false);
  assert.equal(await verifyManifestState(secret, "legacy-random-state", 1000), false);

  const future = await buildManifestState(secret, 1301);
  assert.equal(await verifyManifestState(secret, future, 1000), false);
});


test("legacy manifest callback recovers from stored credentials", async () => {
  const now = Math.floor(Date.now() / 1000);
  const setupToken = `v1.${now}.setup-secret`;
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    webhook_secret: "webhook-secret",
    slug: "cwb-preflight-dev",
  };
  const env = {
    CWB_SETUP_TOKEN: setupToken,
    CWB_STATE: {
      async get(key) {
        assert.equal(key, "github-app-credentials");
        return JSON.stringify(stored);
      },
    },
  };
  const request = new Request(
    "https://cwb.example.workers.dev/setup/github/callback?code=unused&state=legacy-state",
    {
      headers: {
        Cookie: `cwb_setup=${setupToken}`,
      },
    },
  );

  const response = await worker.fetch(request, env);

  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /GitHub App created/);
  assert.match(body, /Install this GitHub App/);
});

test("async route failures are converted to service errors", async () => {
  const env = {
    CWB_STATE: {
      async get() {
        return null;
      },
    },
  };
  const request = new Request(
    "https://cwb.example.workers.dev/webhooks/github",
    {
      method: "POST",
      body: "{}",
    },
  );

  const response = await worker.fetch(request, env);

  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), { error: "service error" });
});

async function testPrivateKeyPem() {
  const keys = await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 1024,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  );
  const der = new Uint8Array(
    await crypto.subtle.exportKey("pkcs8", keys.privateKey),
  );
  const base64 = Buffer.from(der).toString("base64");
  const wrapped = base64.match(/.{1,64}/g)?.join("\n") || base64;
  return `-----BEGIN PRIVATE KEY-----\n${wrapped}\n-----END PRIVATE KEY-----`;
}

async function webhookSignature(secret, body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = new Uint8Array(
    await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)),
  );
  return "sha256=" + Array.from(
    digest,
    (value) => value.toString(16).padStart(2, "0"),
  ).join("");
}

test("Marketplace OAuth state binds installation and is short-lived", async () => {
  const secret = "github-client-secret";
  const state = await buildMarketplaceOAuthState(secret, 2468, 1000);

  assert.deepEqual(
    await parseMarketplaceOAuthState(secret, state, 1000),
    { installation_id: 2468 },
  );
  assert.equal(await verifyMarketplaceOAuthState(secret, state, 1000), true);
  assert.equal(await verifyMarketplaceOAuthState(secret, state, 1600), true);
  assert.equal(await verifyMarketplaceOAuthState(secret, state, 1601), false);
  assert.equal(
    await verifyMarketplaceOAuthState("different-secret", state, 1000),
    false,
  );

  const parts = state.split(".");
  const tampered = [
    parts[0],
    parts[1],
    parts[2],
    "9999",
    parts[4],
  ].join(".");
  assert.equal(await verifyMarketplaceOAuthState(secret, tampered, 1000), false);
});

test("Marketplace purchase normalizes only supported lifecycle actions", () => {
  const purchased = normalizeMarketplacePurchase("marketplace_purchase", {
    action: "purchased",
    effective_date: "2026-09-23T00:00:00Z",
    marketplace_purchase: {
      account: { id: 123 },
      plan: { id: 456 },
    },
  });
  assert.deepEqual(purchased, {
    disposition: "marketplace",
    action: "purchased",
    account_id: 123,
    active: true,
    plan_id: 456,
    effective_date: "2026-09-23T00:00:00Z",
  });

  const cancelled = normalizeMarketplacePurchase("marketplace_purchase", {
    action: "cancelled",
    marketplace_purchase: {
      account: { id: 123 },
      plan: { id: 456 },
    },
  });
  assert.equal(cancelled.active, false);
  assert.equal(
    normalizeMarketplacePurchase("marketplace_purchase", {
      action: "pending_change",
    }).disposition,
    "ignored",
  );
  assert.equal(normalizeMarketplacePurchase("ping", {}).disposition, "ping");
});

test("Marketplace account keys do not contain account names", () => {
  assert.equal(marketplaceAccountKey(12345), "marketplace-account:12345");
  assert.throws(() => marketplaceAccountKey(0));
  assert.throws(() => marketplaceAccountKey("12345"));
});

test("Marketplace setup binds GitHub installation before OAuth", async () => {
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    webhook_secret: "app-webhook-secret",
    slug: "cwb-preflight",
  };
  const env = {
    CWB_GITHUB_CLIENT_SECRET: "client-secret",
    CWB_STATE: {
      async get(key) {
        assert.equal(key, "github-app-credentials");
        return JSON.stringify(stored);
      },
    },
  };

  const response = await worker.fetch(
    new Request(
      "https://cwb.example.workers.dev/marketplace/setup?installation_id=2468",
    ),
    env,
  );

  assert.equal(response.status, 302);
  const location = new URL(response.headers.get("Location"));
  assert.equal(location.origin, "https://github.com");
  assert.equal(location.pathname, "/login/oauth/authorize");
  assert.equal(location.searchParams.get("client_id"), "Iv1.client");
  assert.equal(
    location.searchParams.get("redirect_uri"),
    "https://cwb.example.workers.dev/marketplace/oauth/callback",
  );
  const state = location.searchParams.get("state");
  assert.ok(state);
  assert.deepEqual(
    await parseMarketplaceOAuthState("client-secret", state),
    { installation_id: 2468 },
  );

  const invalid = await worker.fetch(
    new Request("https://cwb.example.workers.dev/marketplace/setup"),
    env,
  );
  assert.equal(invalid.status, 400);
});

test("Marketplace OAuth callback verifies access to the bound installation", async (t) => {
  const clientSecret = "client-secret";
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    webhook_secret: "app-webhook-secret",
    slug: "cwb-preflight",
  };
  const env = {
    CWB_GITHUB_CLIENT_SECRET: clientSecret,
    CWB_STATE: {
      async get(key) {
        assert.equal(key, "github-app-credentials");
        return JSON.stringify(stored);
      },
    },
  };
  const state = await buildMarketplaceOAuthState(
    clientSecret,
    2468,
  );
  const requests = [];

  t.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = String(input);
    requests.push({ url, method: init.method || "GET" });

    if (url === "https://github.com/login/oauth/access_token") {
      return new Response(
        JSON.stringify({ access_token: "temporary-user-token" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url === "https://api.github.com/user") {
      return new Response(
        JSON.stringify({ id: 42, login: "octocat" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url.includes("/user/installations?")) {
      return new Response(
        JSON.stringify({
          total_count: 1,
          installations: [{ id: 2468 }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (
      url === "https://api.github.com/applications/Iv1.client/token" &&
      init.method === "DELETE"
    ) {
      assert.match(String(init.headers.Authorization), /^Basic /);
      assert.equal(
        JSON.parse(init.body).access_token,
        "temporary-user-token",
      );
      return new Response(null, { status: 204 });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  const response = await worker.fetch(
    new Request(
      "https://cwb.example.workers.dev/marketplace/oauth/callback" +
        `?code=temporary-code&state=${encodeURIComponent(state)}`,
    ),
    env,
  );

  assert.equal(response.status, 200);
  assert.match(await response.text(), /octocat/);
  assert.equal(requests.length, 4);
});

test("Marketplace OAuth callback rejects spoofed installation after revoking token", async (t) => {
  const clientSecret = "client-secret";
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    webhook_secret: "app-webhook-secret",
    slug: "cwb-preflight",
  };
  const env = {
    CWB_GITHUB_CLIENT_SECRET: clientSecret,
    CWB_STATE: {
      async get() {
        return JSON.stringify(stored);
      },
    },
  };
  const state = await buildMarketplaceOAuthState(
    clientSecret,
    2468,
  );
  let revoked = false;

  t.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = String(input);
    if (url === "https://github.com/login/oauth/access_token") {
      return new Response(
        JSON.stringify({ access_token: "temporary-user-token" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url === "https://api.github.com/user") {
      return new Response(
        JSON.stringify({ id: 42, login: "octocat" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url.includes("/user/installations?")) {
      return new Response(
        JSON.stringify({
          total_count: 1,
          installations: [{ id: 9999 }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (
      url === "https://api.github.com/applications/Iv1.client/token" &&
      init.method === "DELETE"
    ) {
      revoked = true;
      return new Response(null, { status: 204 });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  const response = await worker.fetch(
    new Request(
      "https://cwb.example.workers.dev/marketplace/oauth/callback" +
        `?code=temporary-code&state=${encodeURIComponent(state)}`,
    ),
    env,
  );

  assert.equal(response.status, 403);
  assert.equal(revoked, true);
});

test("Marketplace cancellation is recorded and uninstalls the App", async (t) => {
  const secret = "marketplace-webhook-secret";
  const payload = JSON.stringify({
    action: "cancelled",
    effective_date: "2026-09-23T00:00:00Z",
    marketplace_purchase: {
      account: { id: 987 },
      plan: { id: 654 },
    },
  });
  const writes = [];
  const requests = [];
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: await testPrivateKeyPem(),
    webhook_secret: "app-webhook-secret",
    slug: "cwb-preflight",
  };
  const env = {
    CWB_MARKETPLACE_WEBHOOK_SECRET: secret,
    CWB_STATE: {
      async get(key) {
        if (key === "github-app-credentials") return JSON.stringify(stored);
        return null;
      },
      async put(key, value, options) {
        writes.push({ key, value: JSON.parse(value), options });
      },
    },
  };

  t.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = String(input);
    requests.push({ url, method: init.method || "GET" });
    if (url.includes("/app/installations?")) {
      return new Response(
        JSON.stringify([
          {
            id: 2468,
            account: { id: 987 },
            target_id: 987,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url.endsWith("/app/installations/2468") && init.method === "DELETE") {
      return new Response(null, { status: 202 });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  const response = await worker.fetch(
    new Request("https://cwb.example.workers.dev/webhooks/marketplace", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-GitHub-Event": "marketplace_purchase",
        "X-GitHub-Delivery": "marketplace-delivery",
        "X-Hub-Signature-256": await webhookSignature(secret, payload),
      },
      body: payload,
    }),
    env,
  );

  assert.equal(response.status, 202);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].key, "marketplace-account:987");
  assert.equal(writes[0].value.active, false);
  assert.equal(writes[0].value.plan_id, 654);
  assert.deepEqual(writes[0].options, { expirationTtl: 2592000 });
  assert.equal(requests.length, 2);
  assert.match(requests[0].url, /\/app\/installations\?/);
  assert.deepEqual(requests[1], {
    url: "https://api.github.com/app/installations/2468",
    method: "DELETE",
  });
});

test("Marketplace cancellation stays blocked if uninstall API fails", async (t) => {
  const secret = "marketplace-webhook-secret";
  const payload = JSON.stringify({
    action: "cancelled",
    marketplace_purchase: {
      account: { id: 987 },
      plan: { id: 654 },
    },
  });
  const writes = [];
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: await testPrivateKeyPem(),
    webhook_secret: "app-webhook-secret",
    slug: "cwb-preflight",
  };
  const env = {
    CWB_MARKETPLACE_WEBHOOK_SECRET: secret,
    CWB_STATE: {
      async get(key) {
        if (key === "github-app-credentials") return JSON.stringify(stored);
        return null;
      },
      async put(key, value, options) {
        writes.push({ key, value: JSON.parse(value), options });
      },
    },
  };

  t.mock.method(globalThis, "fetch", async () => {
    return new Response("temporary failure", { status: 503 });
  });

  const response = await worker.fetch(
    new Request("https://cwb.example.workers.dev/webhooks/marketplace", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-GitHub-Event": "marketplace_purchase",
        "X-GitHub-Delivery": "marketplace-delivery-failed-uninstall",
        "X-Hub-Signature-256": await webhookSignature(secret, payload),
      },
      body: payload,
    }),
    env,
  );

  assert.equal(response.status, 500);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].key, "marketplace-account:987");
  assert.equal(writes[0].value.active, false);
  assert.deepEqual(writes[0].options, { expirationTtl: 2592000 });
});

test("Marketplace deactivation treats missing installation as already inactive", async (t) => {
  const credentials = {
    client_id: "Iv1.client",
    pem: await testPrivateKeyPem(),
  };
  t.mock.method(globalThis, "fetch", async () => {
    return new Response("[]", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  assert.equal(
    await deactivateMarketplaceInstallation(credentials, 987),
    false,
  );
});

test("cancelled Marketplace account is not queued for scans", async () => {
  const appSecret = "app-webhook-secret";
  const payload = JSON.stringify({
    after: "a".repeat(40),
    ref: "refs/heads/main",
    repository: {
      full_name: "octo/demo",
      private: false,
      owner: { id: 777 },
    },
    installation: { id: 1234 },
  });
  let queued = false;
  const stored = {
    app_id: 123,
    client_id: "Iv1.client",
    pem: "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    webhook_secret: appSecret,
    slug: "cwb-preflight",
  };
  const env = {
    CWB_STATE: {
      async get(key) {
        if (key === "github-app-credentials") return JSON.stringify(stored);
        if (key === "marketplace-account:777") {
          return JSON.stringify({ active: false });
        }
        return null;
      },
    },
    SCAN_QUEUE: {
      async send() {
        queued = true;
      },
    },
  };
  const response = await worker.fetch(
    new Request("https://cwb.example.workers.dev/webhooks/github", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": "push-delivery",
        "X-Hub-Signature-256": await webhookSignature(appSecret, payload),
      },
      body: payload,
    }),
    env,
  );

  assert.equal(response.status, 202);
  const body = await response.json();
  assert.equal(body.disposition, "marketplace-cancelled");
  assert.equal(queued, false);
});

