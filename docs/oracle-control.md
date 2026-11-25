# Oracle integration: phase 1

This change reads only the last report from the existing host booking service. It does not call systemd, execute a browser, change a schedule, or enable a second booking provider.

Configure ORACLE_BOOKING_REPORT to the path of a sanitized JSON report inside the gateway container. Prefer publishing a copy of the report to an existing persistent volume using a privileged host-side publisher that has no incoming network interface. Do not mount the private booking directory, token files, host socket, or Docker socket into the application container.

Deployment must be coordinated with the host operator: wait until no booking job is running, preserve the private checkout and Gmail scripts and browser profile, and verify the report endpoint using the existing authenticated HTTPS gateway before releasing the APK. Do not blindly recreate the live container: private files may not be in the image. No deployment or live test is claimed by this change.

The report endpoint returns available:false for a missing or invalid report. The screen displays the timestamp and does not represent a historical report as current service state. Future phases need a narrow authenticated host control interface, actual systemd status, schedule controls, and confirmed seat details; these are not implemented here.
