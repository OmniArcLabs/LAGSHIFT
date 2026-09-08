# GameLink architecture

GameLink is an orchestration and access layer, not a new cryptographic
primitive. The client selects among measured Hysteria2, REALITY and future
MASQUE routes. The control plane issues short-lived, revocable sessions and
the gateway enforces byte quota at the point where traffic actually passes.

Turbo mode requires two authenticated data paths to terminate in the same
gateway session. The client may add XOR parity or duplicate selected datagrams;
the gateway de-duplicates by `(session_id, sequence)` before forwarding a
single packet to the game server. Sending duplicates through unrelated public
proxies is forbidden because it would expose two source IPs and break sessions.

Anonymous radar is disabled by default. Its schema deliberately has no IP,
server address, config name, account ID, device ID, destination or process.
The API must reject unknown properties and discard raw request IPs from
application logs where operationally possible.

The authoritative quota fields are `used_bytes`, `limit_bytes` and
`resets_at`. Client-side counters are only a display estimate and must never
authorize additional traffic.
