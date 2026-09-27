# syntax=docker/dockerfile:1.7
FROM cloudflare/cloudflared:2026.9.3 AS cloudflared

FROM python:3.13-slim-bookworm AS runtime

# Keep the upstream cloudflared binary and trust store exact while adding only a
# small, testable process supervisor. The supervisor never talks to Docker.
COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY --from=cloudflared /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY deploy/local-host/tunnel/supervisor.py /opt/alto-tunnel/supervisor.py

ENTRYPOINT ["python", "/opt/alto-tunnel/supervisor.py"]
