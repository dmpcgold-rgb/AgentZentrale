# AgentZentrale backup and disaster-recovery runbook

## Current guarantees and limitations

- `scripts/backup-agentzentrale.sh` streams `/app/server/data` into a GPG AES-256 encrypted archive. The plaintext tar stream is not written to a local archive file.
- `scripts/verify-backup-archive.sh` checks decryption, gzip/tar structure, and rejects unsafe tar members. This verifies archive readability, **not application-level consistency**.
- The application writes to a named Docker volume (`agent-data`). The current backup is taken while the container is running. Files may change during tar traversal; browser profile and JSON files may be inconsistent even when verification passes.
- The current backup script retains local archives for approximately 14 days. Offsite Google Drive upload and recovery have **not** been validated by the CI tests.
- Losing the encryption passphrase makes the backups unrecoverable. Keep an independently protected recovery copy outside the server.

## Safe, read-only verification of an existing encrypted backup

On a trusted host with the archive and its matching passphrase file:

```bash
bash scripts/verify-backup-archive.sh /secure/path/agentzentrale-YYYYMMDDTHHMMSSZ.tar.gz.gpg /secure/path/backup-passphrase
```

Do not print or commit the passphrase. The verifier does not extract files or change the running service.

## Controlled disaster-recovery drill (requires explicit operator approval)

1. Select one verified, offsite encrypted backup; record its timestamp, size, and SHA-256 checksum. Confirm the remote copy's checksum matches the local copy before decrypting.
2. Provision a **separate isolated recovery host or volume**. Do not mount the production `agent-data` volume, reuse production credentials, or expose the restored browser profile to the public internet.
3. Verify the archive with `verify-backup-archive.sh`. Inspect member paths and file types before any extraction.
4. Restore only into a fresh, private staging directory. Preserve restrictive permissions; do not extract as root into the host filesystem. Never use an unreviewed archive with `tar -x`.
5. Check the restored JSON and application state for semantic consistency, including partial writes and browser profile corruption. Start the service in isolation only after credentials/network egress are appropriately disabled.
6. Record recovery time (RTO), age of the newest recoverable state (RPO), validation results, and cleanup of staging data.
7. Keep the production service unchanged throughout the drill.

## Before claiming production-grade recovery

- Add application-level quiescing or atomic snapshots for mutable state; do not assume `tar` of a live browser profile is transactionally consistent.
- Verify the scheduled backup actually runs, offsite sync succeeds, retention is appropriate, and failures generate alerts.
- Perform a controlled offsite restore drill and document its result.
- Separately protect the passphrase and test key recovery.
