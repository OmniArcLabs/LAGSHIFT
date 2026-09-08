const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "x-content-type-options": "nosniff",
  "cache-control": "no-store",
};

function json(value, status = 200, extra = {}) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { ...JSON_HEADERS, ...extra },
  });
}

async function readJson(request, maximumBytes) {
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > maximumBytes) throw new Error("body-too-large");
  const text = await request.text();
  if (new TextEncoder().encode(text).length > maximumBytes) throw new Error("body-too-large");
  return JSON.parse(text);
}

function validDeviceKey(value) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{43}$/.test(value);
}

function base64url(bytes) {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function sessionToken(secret, deviceKey, expiresAt) {
  const payload = base64url(new TextEncoder().encode(JSON.stringify({
    v: 1, sub: deviceKey, exp: Math.floor(expiresAt / 1000), scope: "bootstrap",
  })));
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return `${payload}.${base64url(new Uint8Array(signature))}`;
}

async function bootstrap(request, env) {
  if (!env.SESSION_SIGNING_SECRET || env.SESSION_SIGNING_SECRET.length < 32) {
    return json({ error: "server-not-configured" }, 503);
  }
  if (env.BOOTSTRAP_ACCESS_TOKEN) {
    const expected = `Bearer ${env.BOOTSTRAP_ACCESS_TOKEN}`;
    if (request.headers.get("authorization") !== expected) return json({ error: "unauthorized" }, 401);
  }
  let body;
  try { body = await readJson(request, 16 * 1024); }
  catch { return json({ error: "invalid-request" }, 400); }
  if (!validDeviceKey(body.device_public_key) || !Array.isArray(body.capabilities)) {
    return json({ error: "invalid-device" }, 400);
  }
  const now = Date.now();
  const expiresAt = now + 15 * 60 * 1000;
  const token = await sessionToken(env.SESSION_SIGNING_SECRET, body.device_public_key, expiresAt);
  return json({
    session_token: token,
    expires_at: new Date(expiresAt).toISOString(),
    quota: { plan: "local", remaining_bytes: 0, reset_at: null },
    routes: [],
  });
}

async function radar(request, env) {
  if (env.RADAR_ENABLED !== "true") return json({ error: "radar-disabled" }, 404);
  let samples;
  try { samples = await readJson(request, 64 * 1024); }
  catch { return json({ error: "invalid-request" }, 400); }
  if (!Array.isArray(samples) || samples.length > 100) return json({ error: "invalid-samples" }, 400);
  const allowed = new Set(["score", "latency", "jitter", "loss", "mode", "protocol", "hour", "os",
    "country", "asn", "adapter_kind", "purpose"]);
  const numeric = ["score", "latency", "jitter", "loss"];
  const textual = ["mode", "protocol", "hour", "os", "country", "asn", "adapter_kind", "purpose"];
  if (samples.some((row) => !row || typeof row !== "object" || Array.isArray(row)
      || Object.keys(row).some((key) => !allowed.has(key))
      || numeric.some((key) => row[key] != null && (!Number.isFinite(Number(row[key])) || Math.abs(Number(row[key])) > 100000))
      || textual.some((key) => row[key] != null && (typeof row[key] !== "string" || row[key].length > 64)))) {
    return json({ error: "invalid-samples" }, 400);
  }
  if (env.RADAR) {
    for (const row of samples) {
      env.RADAR.writeDataPoint({
        blobs: [String(row.mode || ""), String(row.protocol || ""), String(row.os || ""),
          String(row.country || ""), String(row.asn || ""), String(row.adapter_kind || ""),
          String(row.purpose || "")],
        doubles: [Number(row.score || 0), Number(row.latency || 0), Number(row.jitter || 0), Number(row.loss || 0)],
        indexes: [String(row.hour || "unknown").slice(0, 32)],
      });
    }
  }
  return new Response(null, { status: 204, headers: { "cache-control": "no-store" } });
}

function networkHint(request) {
  const cf = request.cf || {};
  return json({
    country: String(cf.country || "").slice(0, 2),
    region: String(cf.region || cf.regionCode || "").slice(0, 64),
    city: String(cf.city || "").slice(0, 64),
    asn: Number(cf.asn || 0),
    operator: String(cf.asOrganization || "").slice(0, 80),
  }, 200, { "cache-control": "private, no-store", "permissions-policy": "geolocation=()" });
}

function downloadProbe(request) {
  const requested = Number(new URL(request.url).searchParams.get("bytes") || 0);
  const allowed = new Set([512 * 1024, 3 * 1024 * 1024, 4 * 1024 * 1024]);
  if (!allowed.has(requested)) return json({ error: "invalid-probe-size" }, 400);
  return new Response(new Uint8Array(requested), {
    status: 200,
    headers: {
      "content-type": "application/octet-stream",
      "content-length": String(requested),
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

async function signedDocument(env, key) {
  if (!env.RELEASES) return json({ error: "release-store-unavailable" }, 503);
  const value = await env.RELEASES.get(key);
  if (!value) return json({ error: "not-found" }, 404);
  return new Response(value, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "x-content-type-options": "nosniff",
      "cache-control": "public, max-age=300",
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, service: "lagshift-control-plane", relay: false });
    }
    if (request.method === "POST" && url.pathname === "/v1/client/bootstrap") return bootstrap(request, env);
    if (request.method === "POST" && url.pathname === "/v1/radar/batch") return radar(request, env);
    if (request.method === "GET" && url.pathname === "/v1/network/hint") return networkHint(request);
    if (request.method === "GET" && url.pathname === "/v1/probe/download") return downloadProbe(request);
    if (request.method === "GET" && url.pathname === "/v1/release/manifest") {
      return signedDocument(env, "update-manifest");
    }
    if (request.method === "GET" && url.pathname === "/v1/app-profiles/manifest") {
      return signedDocument(env, "app-profile-manifest");
    }
    return json({ error: "not-found" }, 404);
  },
};
