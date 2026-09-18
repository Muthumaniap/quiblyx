# Deployment boundary

The root Dockerfiles and Compose file target isolated development, not public production. Compose binds exposed ports to loopback. Its fixed database passwords are local-only and are not production secrets.

Before staging: supply managed PostgreSQL/Redis, TLS ingress, managed secret encryption, OIDC browser sessions, private networking, egress rules, object encryption/retention and least-privilege roles. Disable development identity. Run migrations as a one-shot release job, then separately roll control, gateway and workers. Gateway has a 30-second graceful shutdown window; stream draining still requires qualification. Keep old images for application rollback. Database changes must use expand/migrate/contract; initial migration intentionally refuses destructive downgrade.

Readiness endpoints check required authorities. Do not expose readiness failures or internal exception details publicly. Add platform metrics, error alerts and on-call ownership before a pilot. No availability, throughput or recovery targets have been demonstrated.
