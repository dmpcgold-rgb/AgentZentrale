# Private n8n integration (stage 1)

Use the existing Oracle host and Compose project. This overlay adds an isolated n8n service to the existing default Compose network; it does not modify the agent service, its data volume, or WESTbahn scheduling. Do not expose port 5678 publicly. Use an SSH tunnel or an authenticated TLS reverse proxy. The editor requires initial owner setup. Keep n8n updated and retain the upstream license.

## Deployment
Create a private deployment environment file outside Git with N8N_IMAGE set to a verified supported version of docker.n8n.io/n8nio/n8n (not latest), and N8N_ENCRYPTION_KEY set to a securely generated random value. Back up the key and n8n data volume. From the existing project directory:
```sh
docker compose --env-file /opt/agentzentrale-private/n8n.env -f compose.yaml -f compose.n8n.yaml config --quiet
docker compose --env-file /opt/agentzentrale-private/n8n.env -f compose.yaml -f compose.n8n.yaml up -d --no-deps n8n
curl --fail http://127.0.0.1:5678/healthz
```
If the existing deployment relies on Compose interpolation from another environment file, preserve that file as an additional --env-file. Never commit secrets. Use SSH local forwarding to 127.0.0.1:5678; configure TLS or a secure local browser context for owner setup. Do not disable secure cookies for remote HTTP access.

## First workflow
Import `n8n/workflows/agent-status.json` in n8n. Set a distinct random N8N_READ_TOKEN (at least 32 characters) in the private server/.env, then rebuild/recreate the agent service in a maintenance window, preserving its volume. In n8n create a Header Auth credential with name Authorization and value Bearer followed by the scoped token. Select it on the HTTP Request node and run manually. The workflow is inactive by default. Never use the administrator token. Confirm actual response and auth in the live environment before activating. Do not give an AI node unrestricted access to the API.

## Task workflows and checks
Set a separate random N8N_TASK_TOKEN in the private server/.env. Configure a separate Header Auth credential in n8n for the five task workflows (master-status, github-build-status, quality-status, gmail-connection-status, hourly-monitoring). Keep hourly monitoring inactive until manual smoke tests pass. GitHub Actions status requires Actions read permission when using a token. The history stores at most 100 metadata records in the existing agent volume; replay protection is in-memory only. GitHub reads may retry once; allow at least 60 seconds for the build workflow response. No email sending or booking is exposed by these workflows.

## Validation
Run npm test from repository root with Node 22. Check Compose configuration before deployment. Verify both scoped tokens cannot access /chat or /westbahn/run. The existing Android pipeline produces a test APK and is not proof of production signing. Do not merge or deploy before checks pass.

## Subsequent integration
Inventory actual backend routes and introduce scoped service credentials, explicit allowlists and idempotent job IDs before enabling job dispatch. Keep existing WESTbahn scheduler authoritative until a tested handover; do not activate duplicate booking triggers or retry ambiguous checkout results. Preserve zero-price enforcement and existing ledger. Gmail read-only first; no email sending without explicit approval. Test with simulated provider responses before real transactions. Android UI uses the existing gateway authentication to display a read-only automation status.

## Rollback
Stop only n8n with the same Compose files and environment options. Keep its volume for recovery; do not use down -v. Existing agent remains unchanged.
