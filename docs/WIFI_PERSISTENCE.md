# Saved recovery Wi-Fi and automatic reconnect

TWRP remembers successful WLAN connections in
`/data/twrp/wifi/wpa_supplicant.conf`. The directories are root-owned `0700`
and the saved file is `0600`. No personal SSID or password is built into recovery,
included in Git, or printed by the profile helper.

This is intentionally outside `/data/media`, `/data/user/0`, and other
credential-encrypted (CE) user directories. The helper checks that its directory
has **no fscrypt policy** before saving/loading: it must not depend on user-0's
PIN key. The enclosing Android metadata-encrypted `/data` filesystem still has
to be mounted (read-only is enough to load; saving requires read/write).
If TWRP cannot mount `/data` at all, saved credentials
there are unavailable. Formatting `/data` also erases them. A PIN decryption
failure alone need not prevent saved Wi-Fi from working.

Do not move this to `/data/misc/twrp`: the tested phone's `/data/misc` propagates
an fscrypt policy to new subdirectories. Directly under `/data`, the selected
`twrp/wifi` directory and saved file were checked to have no fscrypt policy.

These are supplicant-format credentials, not an encrypted password vault. They
may contain a reusable PSK/passphrase and are accessible to a process with root
access to mounted `/data`. This deliberately supports the owner's request for
network availability before user unlock; do not copy profiles into public logs,
backup manifests, release artifacts, or source control.

## Startup and connection

The existing fstab-ready Wi-Fi initialization runs independently of successful
PIN entry. Before starting supplicant, `twrp-wifi-manager prepare` loads saved
networks into `/tmp/recovery/wifi/wpa_supplicant.conf`. This private RAM directory
is owned by Android's Wi-Fi UID (`1010`), because the recovery supplicant drops
root privileges. Its `SAVE_CONFIG` can therefore work without writing the
read-only active-slot vendor firmware configuration.

Supplicant scans and associates with enabled saved networks automatically. The
background controller also requests scans while disconnected, obtains DHCP,
publishes DNS through the existing root helper, and publishes connected status
only after association, a usable IPv4 address, a default route and resolver
setup. It clears status on disconnect. The GUI mirrors that state once per
second, including after theme reloads. No network work runs on the GUI thread.
This state is not proof of Internet access through a captive portal.
The empty RAM configuration retains supported authentication defaults from the
active vendor config without copying vendor profiles or writing firmware.

If `/data` appears after Wi-Fi starts, the controller loads saved profiles when
the runtime list is empty; it does not replace an in-progress manual connection.
Authenticated RAM-only profiles are saved once the data directory becomes
available. The existing WLAN page still supports manual scanning/connection.
Successful authentication saves the profile even if DHCP initially fails.
Connecting to another network no longer erases all remembered networks. Failed
new entries are removed. Saved entries disabled by `SELECT_NETWORK` are enabled
again in the next boot's runtime copy. Stop Service stops automatic connection;
Start Service starts the normal loader/controller again.

## Verification and scope

Run `python3 -B device/oplus/infiniti/scripts/test-wifi-profiles.py .` for native
host fixtures covering save/load, a real Unix control-socket exchange, multiple
networks, absent/read-only data, malformed/truncated files, size limits,
symlinks/hardlinks, permissions and preservation of the previous backup on
failure. `scripts/apply-recovery-patches.sh` runs these with the existing tests.

`twrp-wifi-manager status` reports mount/key independence/profile count without
displaying keys. `prepare`, `save`, `once` and `daemon` are recovery-only commands.
Runtime testing of a new helper/supplicant configuration is separate from
flashing an image and from testing a fresh recovery boot before PIN entry.
Do not claim the latter from an already-decrypted session.
