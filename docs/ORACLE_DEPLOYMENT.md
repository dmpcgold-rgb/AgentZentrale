# Oracle deployment without Termux / ZIP
This is the **existing** AgentZentrale project, not a second installation.
Use GitHub Actions: **Oracle AgentZentrale - safe manual deployment** and start with `mode=check`.
The GitHub Actions secrets must be set by the repository owner:
- `ORACLE_HOST`: Oracle host/address (never commit it).
- `ORACLE_USER`: SSH user, typically `ubuntu`.
- `ORACLE_SSH_KEY`: dedicated SSH private key permitted to log into Oracle (never paste in chat or commit).
- `ORACLE_KNOWN_HOSTS`: verified SSH host-key line, obtained through an independent trusted fingerprint check.

This workflow will not book a ticket. It updates only the existing application after multiple checks.
**Important current limitation (20 Nov 2026):** The server has uncommitted/untracked changes and the real checkout script exists only on Oracle. Rebuilding Docker now risks removing it. The preflight intentionally **refuses to deploy** until the server-specific code is backed up, reviewed for secrets and personal booking information, moved into a **private** repository (or secure internal deployment artifact), and the Git working tree reconciled. Do not commit saved login profiles, cookies, booking ledger, tickets, addresses, personal tickets, or credentials to this public repository.
Never reset the server or delete checkout markers to work around these checks.
After Oracle source has been reconciled, a manual `mode=apply` starts a sequential clean build and replaces the existing container, preserving the named data volume. No automatic booking action is started by the workflow.
