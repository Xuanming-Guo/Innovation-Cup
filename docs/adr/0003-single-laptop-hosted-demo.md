# ADR 0003: Single-laptop hosted-demo runtime

- Status: accepted for the Innovation Cup demo
- Date: 2026-09-26
- Decision owner: founder
- Related issue: [#37](https://github.com/Xuanming-Guo/Innovation-Cup/issues/37)

## Context

The desktop application needs a public HTTPS FastAPI endpoint and a continuously running durable
worker. The founder selected a no-hosting-bill demo path in which exactly one laptop hosts those
processes, while managers and employees use only installed desktop applications. A Cloudflare
Quick Tunnel can expose the API without router port forwarding, but its random hostname can
change whenever the tunnel restarts.

The desktop must not contain database passwords or a service-role key. It also must not send a
Supabase access token to an unauthenticated, stale or manually entered endpoint.

## Decision

The selected hosted-demo topology is:

```text
installed desktop -> Supabase Auth -> authenticated endpoint-discovery RPC
                  -> Cloudflare Quick Tunnel -> laptop FastAPI container

laptop Docker Compose -> FastAPI + durable worker + tunnel + endpoint registrar
shared system of record -> hosted Supabase
```

The registrar publishes a canonical Quick Tunnel HTTPS origin only after `/health/ready` succeeds.
The private database row is a single-host lease with a persisted instance UUID, a 30-second
heartbeat and a 120-second expiry. Publication and release require the API runtime role plus a
current company-administrator actor/company/purpose context. A second host cannot replace a live
lease. Only an authenticated active company member can call the narrow public discovery RPC.

The desktop resolves the endpoint after Supabase sign-in and re-resolves during authorised
refresh, so a restarted tunnel does not require rebuilding installers. The API and worker retain
separate least-privileged database logins. The manager still configures the company Google AI
credential through Connections; no provider credential is part of host or installer configuration.

## Consequences

- The host laptop needs Docker Desktop, Node 24, Git, the repository clone and one ignored
  `deploy/local-host/.env` file.
- Manager and employee devices need only the correct installer and login credentials.
- The host laptop must remain powered, awake, online and running Docker Desktop.
- Laptop sleep, internet loss, Docker failure or tunnel failure makes the application unavailable;
  the endpoint disappears from discovery after the lease expires.
- Cloudflare Quick Tunnels are free and suitable for a controlled demo, but they are explicitly a
  testing/development facility without a production SLA. A production deployment should use a
  stable named tunnel/domain or another continuously available container host.
- Windows and macOS may warn about the current unsigned/ad-hoc installers. This ADR does not
  change the signing/notarisation gate.

## Rejected alternatives

- Baking a Quick Tunnel URL into installers: it becomes stale after a tunnel restart.
- Putting API/worker database passwords into the desktop: this breaks the server trust boundary.
- Running FastAPI, Gemini and Z3 independently on every employee laptop: it duplicates privileged
  runtime credentials and makes durable shared work dependent on each client process.
- Router port forwarding: it expands the network attack surface and is harder to reproduce across
  arbitrary host laptops.
