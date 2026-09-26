# Tenant identity and private Storage boundary

This document records the implemented identity and tenant-isolation slice. It describes
repository behavior, not proof of a hosted deployment.

## Request path

The desktop sends a Supabase access token as `Authorization: Bearer ...` and the selected company
UUID as `X-Company-ID` to FastAPI. The API accepts only explicitly allowlisted asymmetric JWT
algorithms and verifies the signature through the project's rotating JWKS together with issuer,
audience, expiry, issue time, authenticated role, non-anonymous status, assurance level, subject
and session ID. User-editable JWT metadata is never treated as company membership or authority.

For every company-scoped request, FastAPI opens a database transaction, switches to the
non-owner `coordination_api` role, sets transaction-local actor/company/purpose context, and
resolves a currently active membership. A missing, revoked or other-company membership returns
the same not-found result. Roles come from the membership row, not the token or a client field.

```text
Supabase access token + selected company
  -> asymmetric signature and required-claim verification
  -> transaction-local actor/company context
  -> current active membership under RLS
  -> company-scoped request context
```

Business tables live in the `app` schema, which is absent from the Supabase Data API exposed
schemas. `coordination_api` and `coordination_worker` are non-login, non-owner,
non-`BYPASSRLS` group roles. Composite foreign keys preserve company identity across related
records, and row-level policies fail closed when transaction context is absent.

## Private files

The two buckets are private:

- `coordination-quarantine` receives new uploads.
- `coordination-private` contains only files promoted after a trusted inspection path.

Clients cannot choose an object path and receive no general Storage CRUD policy. The
`storage-ticket` Edge Function authenticates the user, invokes one narrow database function as
the `authenticated` role, and signs only the server-generated operation authorised by that
function. Upload metadata starts in `pending_upload`; finalisation requires an unexpired intent,
the original uploader, declared-size bounds and matching detected MIME type. Promotion and
malware scanning are intentionally a later worker responsibility, so an uploaded object is not
automatically considered safe or available.

Download tickets require the file to be `available` and current source/file access to succeed.
The default signed-download lifetime is 60 seconds and is capped at 300 seconds. Signed URLs
remain usable until their provider expiry; highly sensitive material therefore needs a
re-authorising download proxy rather than a bearer URL.

## Secret placement

The native application may receive only the API origin, Supabase project URL and publishable
client key. Those identify public endpoints and do not bypass RLS. The following remain
server-only environment variables, encrypted Vault values or managed deployment secrets:

- database runtime URLs and passwords;
- Supabase secret/service-role credentials;
- company Gemini API credentials, encrypted in Supabase Vault and plaintext-readable only by the
  durable worker under active tenant context;
- migration-owner credentials.

Only a company administrator can submit, rotate or remove that company's key. The API validates
model access without sending company content and never returns the key. Employees and managers
without company-admin authority cannot read even its metadata. The migration owner is used only
for reviewed schema application. A separately provisioned login inherits one least-privileged
runtime group role. The Edge Function's admin Storage client is used only after the RLS-scoped
database function returns an authorised ticket.

## Operations and evidence

The founder applies reviewed repository migrations manually by following
[`supabase/MIGRATIONS.md`](../../supabase/MIGRATIONS.md). Applied migration history, the immutable
manifest hashes and the reviewed commit SHA must agree. Synthetic demo reset is migration-owner
only and refuses any company not explicitly marked `is_demo`; no real account, employee record,
credential or customer document belongs in seeds or fixtures.
