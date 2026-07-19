# Deployment Patterns (Vercel / Cloudflare / Railway)
Vercel: ideal for Next.js, git-push-to-deploy, environment variables set in dashboard, automatic preview deployments per PR/branch.
Environment variables: never commit secrets to git — use .env.local locally (gitignored) and the platform's env var settings in production.
Database migrations: run migrations as a separate deploy step, not automatically on every request — avoids race conditions with multiple server instances.
Health checks: expose a simple /api/health endpoint returning 200 OK, useful for uptime monitoring and load balancer checks.
