# Oracle integration — controlled deployment

The existing booking service remains the sole booking authority. The mobile gateway reads sanitized reports and current systemd status, and may enqueue only pause, resume and Monday-time changes. No arbitrary commands, start-booking, cancellation or checkout changes.

## Host layout

Provision /var/lib/agentzentrale-control as root-owned, not writable by the container. Its out directory is root-owned and mounted read-only; inbox is a separate directory writable by the gateway's actual mapped UID only. Keep the private booking directory, Docker socket and host systemd socket outside the gateway. The root worker must be installed from reviewed source in a root-owned directory. Set ORACLE_CONTROL_ENABLED=1 on both sides only after verifying ownership, mount separation and the read-only endpoints. Before enabling, ensure inbox is empty. Do not expose the queue over the public internet except via existing authenticated HTTPS gateway.

Host worker: server/host/oracle_status.py. Run once every 20 seconds under a dedicated systemd oneshot timer. Status/report JSON is written atomically; an inactive worker produces unavailable status after two minutes. Gateway environment: ORACLE_HOST_STATUS=/oracle-out/status.json, ORACLE_BOOKING_REPORT=/oracle-out/report.json, ORACLE_CONTROL_OUT=/oracle-out, ORACLE_CONTROL_INBOX=/oracle-inbox. Bind only out (read-only) and inbox (read-write). Expired requests are rejected; accepted requests are not confirmations. Resume may catch up missed timer runs. A schedule change writes a dedicated Monday calendar drop-in and rolls back on command failure. Pause never stops the running booking service. Telegram display shows configuration-file presence, not delivery or bot settings.

## Deployment gate

Do not recreate the live container until all private checkout scripts, Gmail configuration and persistent browser profile are backed up and their restoration verified. Inspect the actual host compose configuration before adapting it. Wait until no booking job is running. Test report endpoint, status expiry, invalid commands and pause/resume in an isolated test unit before activating production controls. Do not enable a second booking scheduler. Preserve application package and existing signing identity; the current Android test workflow does not demonstrate production signing. Run npm test and Android bundle/build checks before release.

No installation, live test, release APK or full Telegram management is claimed by this branch.
