import assert from "node:assert/strict";
import worker from "./src/index.js";

const secret = "0123456789abcdef0123456789abcdef";

let response = await worker.fetch(new Request("https://edge.example/health"), {});
assert.equal(response.status, 200);
assert.deepEqual(await response.json(), { ok: true, service: "lagshift-control-plane", relay: false });

response = await worker.fetch(new Request("https://edge.example/v1/client/bootstrap", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ device_public_key: "A".repeat(43), capabilities: ["radar-v1"] }),
}), { SESSION_SIGNING_SECRET: secret });
assert.equal(response.status, 200);
const bootstrap = await response.json();
assert.equal(bootstrap.routes.length, 0);
assert.equal(bootstrap.quota.remaining_bytes, 0);
assert.match(bootstrap.session_token, /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);

response = await worker.fetch(new Request("https://edge.example/v1/client/bootstrap", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ device_public_key: "bad", capabilities: [] }),
}), { SESSION_SIGNING_SECRET: secret });
assert.equal(response.status, 400);

const signed = JSON.stringify({ version: "1.0.1", signature: "offline-signature" });
response = await worker.fetch(new Request("https://edge.example/v1/release/manifest"), {
  RELEASES: { get: async (key) => key === "update-manifest" ? signed : null },
});
assert.equal(response.status, 200);
assert.equal(await response.text(), signed);

response = await worker.fetch(new Request("https://edge.example/v1/radar/batch", {
  method: "POST", body: "[]",
}), { RADAR_ENABLED: "false" });
assert.equal(response.status, 404);

response = await worker.fetch(new Request("https://edge.example/v1/radar/batch", {
  method: "POST", body: JSON.stringify([{ score: 90, country: "IR", asn: "AS44244",
    purpose: "game", adapter_kind: "mobile" }]),
}), { RADAR_ENABLED: "true" });
assert.equal(response.status, 204);

response = await worker.fetch(new Request("https://edge.example/v1/radar/batch", {
  method: "POST", body: JSON.stringify([{ score: 90, ip: "203.0.113.7" }]),
}), { RADAR_ENABLED: "true" });
assert.equal(response.status, 400);

const hintRequest = new Request("https://edge.example/v1/network/hint");
Object.defineProperty(hintRequest, "cf", { value: {
  country: "IR", region: "Tehran", city: "Tehran", asn: 44244,
  asOrganization: "Example ISP",
} });
response = await worker.fetch(hintRequest, {});
assert.deepEqual(await response.json(), {
  country: "IR", region: "Tehran", city: "Tehran", asn: 44244,
  operator: "Example ISP",
});
assert.equal(response.headers.get("cache-control"), "private, no-store");

response = await worker.fetch(new Request(
  "https://edge.example/v1/probe/download?bytes=524288"
), {});
assert.equal(response.status, 200);
assert.equal((await response.arrayBuffer()).byteLength, 524288);

response = await worker.fetch(new Request(
  "https://edge.example/v1/probe/download?bytes=999"
), {});
assert.equal(response.status, 400);

console.log("Cloudflare Worker contract tests passed");
