const GITHUB_API_VERSION = "2026-03-10";
const GITHUB_ACCEPT = "application/vnd.github+json";
const GITHUB_USER_AGENT = "codex-workspace-bootstrap";
const GITHUB_OWNER = "kohli217";
const GITHUB_REPO = "codex-workspace-bootstrap";
const GITHUB_WORKFLOW = "github-app-worker.yml";
const GITHUB_REF = "main";
const STATE_KEY = "github-app-credentials";
const SETUP_TTL_SECONDS = 3600;
const SETUP_FUTURE_SKEW_SECONDS = 300;
const SUPPORTED_PR_ACTIONS = new Set([
  "opened",
  "reopened",
  "synchronize",
  "ready_for_review",
]);

function textResponse(status, body, headers = {}) {
  return new Response(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/plain; charset=utf-8",
      ...headers,
    },
  });
}

function jsonResponse(status, value, headers = {}) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      ...headers,
    },
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function htmlResponse(status, value, headers = {}) {
  return new Response(value, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/html; charset=utf-8",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      ...headers,
    },
  });
}

function base64urlEncode(bytes) {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function base64urlDecode(value) {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(normalized + padding);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function utf8(value) {
  return new TextEncoder().encode(value);
}

function decodeUtf8(bytes) {
  return new TextDecoder().decode(bytes);
}

function randomToken(bytes = 32) {
  const value = new Uint8Array(bytes);
  crypto.getRandomValues(value);
  return base64urlEncode(value);
}

function timingSafeEqual(left, right) {
  const a = utf8(left);
  const b = utf8(right);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let index = 0; index < a.length; index += 1) diff |= a[index] ^ b[index];
  return diff === 0;
}

function setupTokenIsValid(expected, supplied, now = Math.floor(Date.now() / 1000)) {
  if (!supplied || !timingSafeEqual(expected, supplied)) return false;
  const parts = expected.split(".");
  if (parts.length !== 3 || parts[0] !== "v1" || !parts[2]) return false;
  const issued = Number(parts[1]);
  if (!Number.isInteger(issued) || issued <= 0) return false;
  const age = now - issued;
  return age >= -SETUP_FUTURE_SKEW_SECONDS && age <= SETUP_TTL_SECONDS;
}

function parseCookies(request) {
  const raw = request.headers.get("Cookie") || "";
  const cookies = new Map();
  for (const part of raw.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key && rest.length) cookies.set(key, rest.join("="));
  }
  return cookies;
}

function setupAuthorized(request, env) {
  const received = parseCookies(request).get("cwb_setup");
  return setupTokenIsValid(env.CWB_SETUP_TOKEN, received);
}

function bootstrapPage() {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>CWB GitHub App Setup</title></head><body><h1>CWB GitHub App Setup</h1><p>Authorizing the one-time setup session...</p><noscript>JavaScript is required for the one-time setup link.</noscript><script>const token=new URLSearchParams(location.hash.slice(1)).get('token');if(!token){document.body.append(' Missing setup token.');}else{fetch('/setup/github/session',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({token}),credentials:'same-origin'}).then(r=>{if(!r.ok)throw new Error('authorization failed');history.replaceState(null,'','/setup/github');location.reload();}).catch(()=>document.body.append(' Setup authorization failed.'));}</script></body></html>`;
}

function manifestFor(origin, name = "CWB Preflight Dev") {
  return {
    name,
    url: "https://github.com/kohli217/codex-workspace-bootstrap",
    description: "Repository preflight checks for AI coding readiness and instruction integrity.",
    hook_attributes: {
      url: `${origin}/webhooks/github`,
      active: true,
    },
    redirect_url: `${origin}/setup/github/callback`,
    public: false,
    default_permissions: {
      checks: "write",
      contents: "read",
      pull_requests: "read",
    },
    default_events: ["pull_request", "push"],
    request_oauth_on_install: false,
    setup_on_update: false,
  };
}

function manifestPage(origin, state) {
  const action = `https://github.com/settings/apps/new?state=${encodeURIComponent(state)}`;
  const manifest = JSON.stringify(
    manifestFor(origin, `CWB Preflight Dev ${state.slice(0, 8)}`),
  )
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  return `<!doctype html><html><head><meta charset="utf-8"><title>CWB GitHub App Setup</title></head><body><h1>CWB GitHub App Setup</h1><p>Create the private development GitHub App using the preconfigured minimum permissions.</p><form method="post" action="${action}"><input type="hidden" name="manifest" value="${manifest}"><button type="submit">Create CWB GitHub App</button></form></body></html>`;
}

function derLength(length) {
  if (length < 128) return Uint8Array.of(length);
  const bytes = [];
  let value = length;
  while (value > 0) {
    bytes.unshift(value & 0xff);
    value >>>= 8;
  }
  return Uint8Array.of(0x80 | bytes.length, ...bytes);
}

function der(tag, content) {
  const length = derLength(content.length);
  const result = new Uint8Array(1 + length.length + content.length);
  result[0] = tag;
  result.set(length, 1);
  result.set(content, 1 + length.length);
  return result;
}

function concat(...parts) {
  const length = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function pkcs1ToPkcs8(pkcs1) {
  const version = Uint8Array.of(0x02, 0x01, 0x00);
  const rsaAlgorithm = Uint8Array.of(
    0x30, 0x0d,
    0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01,
    0x05, 0x00,
  );
  return der(0x30, concat(version, rsaAlgorithm, der(0x04, pkcs1)));
}

function pemToPkcs8(pem) {
  const isPkcs1 = pem.includes("BEGIN RSA PRIVATE KEY");
  const isPkcs8 = pem.includes("BEGIN PRIVATE KEY");
  if (!isPkcs1 && !isPkcs8) throw new Error("unsupported GitHub App private key format");
  const base64 = pem
    .replace(/-----BEGIN [^-]+-----/g, "")
    .replace(/-----END [^-]+-----/g, "")
    .replace(/\s+/g, "");
  const derBytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return isPkcs1 ? pkcs1ToPkcs8(derBytes) : derBytes;
}

async function importAppPrivateKey(pem) {
  return crypto.subtle.importKey(
    "pkcs8",
    pemToPkcs8(pem),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function buildAppJwt(clientId, privateKeyPem) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64urlEncode(utf8(JSON.stringify({ alg: "RS256", typ: "JWT" })));
  const payload = base64urlEncode(utf8(JSON.stringify({
    iat: now - 60,
    exp: now + 540,
    iss: clientId,
  })));
  const input = `${header}.${payload}`;
  const key = await importAppPrivateKey(privateKeyPem);
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    utf8(input),
  );
  return `${input}.${base64urlEncode(new Uint8Array(signature))}`;
}

async function loadCredentials(env) {
  const record = await env.CWB_STATE.get(STATE_KEY);
  if (!record) throw new Error("GitHub App credentials are not configured");
  const credentials = JSON.parse(record);
  if (!credentials.client_id || !credentials.pem || !credentials.webhook_secret) {
    throw new Error("stored GitHub App credentials are incomplete");
  }
  return credentials;
}

async function storeCredentials(env, credentials) {
  await env.CWB_STATE.put(STATE_KEY, JSON.stringify(credentials));
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey(
    "raw",
    utf8(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = new Uint8Array(await crypto.subtle.sign("HMAC", key, value));
  return Array.from(digest, (item) => item.toString(16).padStart(2, "0")).join("");
}

async function verifyWebhook(secret, body, signatureHeader) {
  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) return false;
  const expected = `sha256=${await hmacHex(secret, body)}`;
  return timingSafeEqual(expected, signatureHeader);
}

function brokerGrantInput(deliveryId, target) {
  return utf8([
    deliveryId,
    target.event ?? "",
    target.repository ?? "",
    String(target.installation_id ?? ""),
    target.head_sha ?? "",
    target.action ?? "",
    String(target.pull_request_number ?? ""),
    target.merge_commit_sha ?? "",
    target.ref ?? "",
  ].join("\n"));
}

async function brokerGrant(secret, deliveryId, target) {
  return hmacHex(
    secret,
    brokerGrantInput(deliveryId, target),
  );
}

function requiredText(value, name) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`missing ${name}`);
  return value;
}

function positiveInteger(value, name) {
  if (!Number.isInteger(value) || value <= 0) throw new Error(`missing ${name}`);
  return value;
}

function normalizeWebhook(eventName, payload) {
  if (eventName === "ping") return { disposition: "ping" };
  const repository = requiredText(payload?.repository?.full_name, "repository.full_name");
  if (payload?.repository?.private !== false) {
    return { disposition: "private-unsupported" };
  }
  const installationId = positiveInteger(payload?.installation?.id, "installation.id");

  if (eventName === "pull_request") {
    const action = typeof payload.action === "string" ? payload.action : null;
    if (!SUPPORTED_PR_ACTIONS.has(action)) return { disposition: "ignored" };
    const number = positiveInteger(payload.number, "number");
    const headSha = requiredText(payload?.pull_request?.head?.sha, "pull_request.head.sha");
    const mergeSha = payload?.pull_request?.merge_commit_sha;
    return {
      disposition: "scan",
      target: {
        event: "pull_request",
        repository,
        head_sha: headSha,
        installation_id: installationId,
        action,
        pull_request_number: number,
        merge_commit_sha: typeof mergeSha === "string" && mergeSha ? mergeSha : null,
        ref: null,
      },
    };
  }

  if (eventName === "push") {
    const headSha = requiredText(payload.after, "after");
    if (/^0+$/.test(headSha)) return { disposition: "ignored" };
    return {
      disposition: "scan",
      target: {
        event: "push",
        repository,
        head_sha: headSha,
        installation_id: installationId,
        action: null,
        pull_request_number: null,
        merge_commit_sha: null,
        ref: typeof payload.ref === "string" && payload.ref ? payload.ref : null,
      },
    };
  }

  return { disposition: "ignored" };
}

async function exchangeManifestCode(code) {
  const response = await fetch(
    `https://api.github.com/app-manifests/${encodeURIComponent(code)}/conversions`,
    {
      method: "POST",
      headers: {
        Accept: GITHUB_ACCEPT,
        "User-Agent": GITHUB_USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
      },
    },
  );
  if (!response.ok) throw new Error(`manifest conversion failed with HTTP ${response.status}`);
  const body = await response.json();
  if (!body?.client_id || !body?.pem || !body?.webhook_secret) {
    throw new Error("manifest conversion response is incomplete");
  }
  return {
    app_id: body.id,
    client_id: body.client_id,
    pem: body.pem,
    webhook_secret: body.webhook_secret,
    slug: body.slug || null,
  };
}

async function createInstallationToken(credentials, installationId, repository) {
  const appJwt = await buildAppJwt(credentials.client_id, credentials.pem);
  const [, repoName] = repository.split("/");
  if (!repoName) throw new Error("repository must use owner/name form");

  const response = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Accept: GITHUB_ACCEPT,
        Authorization: `Bearer ${appJwt}`,
        "Content-Type": "application/json",
        "User-Agent": GITHUB_USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
      },
      body: JSON.stringify({
        repositories: [repoName],
        permissions: {
          checks: "write",
          contents: "read",
        },
      }),
    },
  );
  if (response.status !== 201) {
    throw new Error(`installation token request failed with HTTP ${response.status}`);
  }
  const body = await response.json();
  if (!body?.token) throw new Error("installation token response is missing token");
  return { token: body.token, expires_at: body.expires_at || null };
}

async function verifyActionsOidc(token, audience) {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("invalid OIDC token");
  const header = JSON.parse(decodeUtf8(base64urlDecode(parts[0])));
  const payload = JSON.parse(decodeUtf8(base64urlDecode(parts[1])));
  if (header.alg !== "RS256" || !header.kid) throw new Error("unsupported OIDC signing key");
  if (payload.iss !== "https://token.actions.githubusercontent.com") throw new Error("invalid OIDC issuer");
  if (payload.aud !== audience) throw new Error("invalid OIDC audience");
  if (payload.repository !== `${GITHUB_OWNER}/${GITHUB_REPO}`) throw new Error("invalid OIDC repository");
  if (payload.ref !== "refs/heads/main") throw new Error("invalid OIDC ref");
  if (payload.event_name !== "workflow_dispatch") throw new Error("invalid OIDC event");
  if (
    payload.workflow_ref !==
    `${GITHUB_OWNER}/${GITHUB_REPO}/.github/workflows/${GITHUB_WORKFLOW}@refs/heads/main`
  ) {
    throw new Error("invalid OIDC workflow");
  }
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(payload.exp) || payload.exp < now - 30) throw new Error("expired OIDC token");
  if (Number.isFinite(payload.nbf) && payload.nbf > now + 30) throw new Error("OIDC token is not active");

  const configResponse = await fetch("https://token.actions.githubusercontent.com/.well-known/openid-configuration");
  if (!configResponse.ok) throw new Error("could not load GitHub OIDC configuration");
  const config = await configResponse.json();
  const jwksResponse = await fetch(config.jwks_uri);
  if (!jwksResponse.ok) throw new Error("could not load GitHub OIDC signing keys");
  const jwks = await jwksResponse.json();
  const jwk = jwks.keys?.find((item) => item.kid === header.kid && item.kty === "RSA");
  if (!jwk) throw new Error("GitHub OIDC signing key was not found");

  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    base64urlDecode(parts[2]),
    utf8(`${parts[0]}.${parts[1]}`),
  );
  if (!valid) throw new Error("GitHub Actions OIDC signature is invalid");
  return payload;
}

function validateQueuedTokenEndpoint(value) {
  if (typeof value !== "string" || !value) {
    throw new Error("queued token endpoint is missing");
  }
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/tokens/github" ||
    !url.hostname.endsWith(".workers.dev")
  ) {
    throw new Error("queued token endpoint is invalid");
  }
  return url.toString().replace(/\/$/, "");
}

async function dispatchWorkflow(env, queued) {
  const tokenEndpoint = validateQueuedTokenEndpoint(queued.token_endpoint);
  const credentials = await loadCredentials(env);
  const grant = await brokerGrant(
    credentials.webhook_secret,
    queued.delivery_id,
    queued.target,
  );
  const payload = base64urlEncode(utf8(JSON.stringify({
    delivery_id: queued.delivery_id,
    broker_grant: grant,
    target: queued.target,
  })));
  const response = await fetch(
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: GITHUB_ACCEPT,
        Authorization: `Bearer ${env.CWB_DISPATCH_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": GITHUB_USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
      },
      body: JSON.stringify({
        ref: GITHUB_REF,
        inputs: {
          payload,
          token_endpoint: tokenEndpoint,
        },
      }),
    },
  );
  if (!response.ok) throw new Error(`workflow dispatch failed with HTTP ${response.status}`);
}

async function handleSetup(request, env) {
  if (!setupAuthorized(request, env)) return htmlResponse(200, bootstrapPage());
  const origin = new URL(request.url).origin;
  const state = randomToken();
  return htmlResponse(200, manifestPage(origin, state), {
    "Set-Cookie": `cwb_manifest_state=${state}; Path=/setup/github; Max-Age=3600; Secure; HttpOnly; SameSite=Lax`,
  });
}

async function handleSetupSession(request, env) {
  const body = await request.text();
  const token = new URLSearchParams(body).get("token");
  if (!setupTokenIsValid(env.CWB_SETUP_TOKEN, token)) return jsonResponse(403, { error: "forbidden" });
  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "no-store",
      "Set-Cookie": `cwb_setup=${env.CWB_SETUP_TOKEN}; Path=/setup/github; Max-Age=3600; Secure; HttpOnly; SameSite=Lax`,
    },
  });
}

async function handleSetupCallback(request, env) {
  if (!setupAuthorized(request, env)) return jsonResponse(403, { error: "forbidden" });
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const expectedState = parseCookies(request).get("cwb_manifest_state");
  if (!code || !state || !expectedState || !timingSafeEqual(state, expectedState)) {
    return jsonResponse(400, { error: "invalid manifest callback" });
  }
  const credentials = await exchangeManifestCode(code);
  await storeCredentials(env, credentials);
  const slug = String(credentials.slug || "");
  const installation = slug
    ? `<p><a href="https://github.com/apps/${encodeURIComponent(slug)}/installations/new">Install this GitHub App</a> on one public test repository.</p>`
    : "<p>Open the GitHub App settings and install it on one public test repository.</p>";
  return htmlResponse(
    200,
    `<!doctype html><html><head><meta charset="utf-8"><title>CWB GitHub App Created</title></head><body><h1>GitHub App created</h1><p>Credentials were encrypted and stored in Cloudflare KV.</p><p>App: ${escapeHtml(slug)}</p>${installation}<p>After installation, push a commit or open/update a pull request.</p></body></html>`,
    {
      "Set-Cookie": "cwb_setup=; Path=/setup/github; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
    },
  );
}

async function handleWebhook(request, env) {
  const rawBody = new Uint8Array(await request.arrayBuffer());
  const credentials = await loadCredentials(env);
  const valid = await verifyWebhook(
    credentials.webhook_secret,
    rawBody,
    request.headers.get("X-Hub-Signature-256"),
  );
  if (!valid) return jsonResponse(401, { error: "invalid webhook signature" });

  let payload;
  try {
    payload = JSON.parse(decodeUtf8(rawBody));
  } catch {
    return jsonResponse(400, { error: "invalid webhook JSON" });
  }
  const eventName = request.headers.get("X-GitHub-Event") || "";
  const deliveryId = request.headers.get("X-GitHub-Delivery") || "";
  if (!deliveryId) return jsonResponse(400, { error: "missing GitHub delivery id" });

  let decision;
  try {
    decision = normalizeWebhook(eventName, payload);
  } catch {
    return jsonResponse(400, { error: "invalid webhook payload" });
  }
  if (decision.disposition === "scan") {
    const origin = new URL(request.url).origin;
    await env.SCAN_QUEUE.send({
      delivery_id: deliveryId,
      target: decision.target,
      token_endpoint: `${origin}/tokens/github`,
    });
  }
  return jsonResponse(202, {
    accepted: true,
    disposition: decision.disposition,
    delivery_id: deliveryId,
  });
}

async function handleTokenBroker(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  if (!authorization.startsWith("Bearer ")) return jsonResponse(401, { error: "missing bearer token" });
  const audience = new URL(request.url).origin + "/tokens/github";
  try {
    await verifyActionsOidc(authorization.slice(7), audience);
  } catch {
    return jsonResponse(401, { error: "invalid GitHub Actions OIDC token" });
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse(400, { error: "invalid JSON" });
  }
  const deliveryId = body?.delivery_id;
  const suppliedGrant = body?.broker_grant;
  const target = body?.target;
  if (typeof deliveryId !== "string" || !deliveryId || typeof suppliedGrant !== "string") {
    return jsonResponse(400, { error: "invalid broker grant" });
  }
  if (!target || typeof target !== "object") {
    return jsonResponse(400, { error: "invalid target" });
  }

  const repository = target.repository;
  const installationId = target.installation_id;
  const headSha = target.head_sha;
  const event = target.event;
  if (typeof repository !== "string" || repository.split("/").length !== 2) {
    return jsonResponse(400, { error: "invalid repository" });
  }
  if (!Number.isInteger(installationId) || installationId <= 0) {
    return jsonResponse(400, { error: "invalid installation_id" });
  }
  if (typeof headSha !== "string" || !headSha || !["push", "pull_request"].includes(event)) {
    return jsonResponse(400, { error: "invalid target" });
  }

  try {
    const credentials = await loadCredentials(env);
    const expectedGrant = await brokerGrant(
      credentials.webhook_secret,
      deliveryId,
      target,
    );
    if (!timingSafeEqual(expectedGrant, suppliedGrant)) {
      return jsonResponse(403, { error: "invalid broker grant" });
    }
    return jsonResponse(
      200,
      await createInstallationToken(credentials, installationId, repository),
    );
  } catch {
    return jsonResponse(502, { error: "GitHub installation token request failed" });
  }
}

export {
  base64urlEncode,
  base64urlDecode,
  brokerGrant,
  manifestFor,
  normalizeWebhook,
  pkcs1ToPkcs8,
  setupTokenIsValid,
  timingSafeEqual,
  validateQueuedTokenEndpoint,
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (request.method === "GET" && url.pathname === "/healthz") {
        return jsonResponse(200, { ok: true, deployment: "cloudflare-free" });
      }
      if (request.method === "GET" && url.pathname === "/setup/github") {
        return handleSetup(request, env);
      }
      if (request.method === "POST" && url.pathname === "/setup/github/session") {
        return handleSetupSession(request, env);
      }
      if (request.method === "GET" && url.pathname === "/setup/github/callback") {
        return handleSetupCallback(request, env);
      }
      if (request.method === "POST" && url.pathname === "/webhooks/github") {
        return handleWebhook(request, env);
      }
      if (request.method === "POST" && url.pathname === "/tokens/github") {
        return handleTokenBroker(request, env);
      }
      return jsonResponse(404, { error: "not found" });
    } catch (error) {
      console.error("CWB Worker request failed", error?.name || "Error");
      return jsonResponse(500, { error: "service error" });
    }
  },

  async queue(batch, env) {
    for (const message of batch.messages) {
      try {
        await dispatchWorkflow(env, message.body);
        message.ack();
      } catch (error) {
        console.error("CWB workflow dispatch failed", error?.name || "Error");
        message.retry();
      }
    }
  },
};
