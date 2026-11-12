# Encrypted Oracle backup (opt-in)

This is **not activated by merging**. It requires a private encryption passphrase and an explicit server-side installation. Never commit the passphrase, backup files or browser profile to GitHub.

1. On Oracle, install `gnupg` and create `/etc/agentzentrale` (mode 700).
2. Create `/etc/agentzentrale/backup-passphrase` as root, with a unique random secret (mode 600). Store an independent copy in a password manager. Without it, backups cannot be restored.
3. Run `sudo bash /opt/agentzentrale/scripts/backup-agentzentrale.sh` manually and verify successful output.
4. Only after manual verification, schedule it using a root-owned systemd timer or cron at 02:30 daily.
5. Store an encrypted copy **off-server**. Local-only backups cannot recover a deleted Oracle instance or disk.
6. Test restoration to an isolated volume before trusting the backups.

The script streams the Docker data directory directly into GPG AES-256 encryption, verifies decryption and tar listing, and retains about 14 days. It does not back up `server/.env`, GitHub secrets, or the operating system. The browser profile is backed up online, so individual files may change during the archive operation; for stronger consistency, plan a maintenance window and stop the application briefly before backup.
