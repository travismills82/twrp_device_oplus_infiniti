# TWRP device tree for ONEPLUS infiniti

## Supported devices

- OnePlus 15 all variants

## Build it yourself

```shell
mkdir twrp && cd twrp
repo init --depth=1 -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp.git -b twrp-16.0
repo sync
git clone --depth=1 https://github.com/travismills82/twrp_device_oplus_infiniti device/oplus/infiniti
```

```shell
source build/envsetup.sh
lunch twrp_infiniti
make recoveryimage
```

If there is no error, `recovery.img` will be found in `out/target/product/infiniti/recovery.img`.

## Flash recovery

```shell
fastboot flash recovery recovery.img
```

or

```shell
fastboot flash recovery_a recovery.img
fastboot flash recovery_b recovery.img
```

## Features

Works:

- [X] ADB
- [X] Display
- [X] Decryption
- [X] Fastbootd
- [X] Flashing
- [X] OTA Flash
- [X] MTP
- [X] Sideload
- [X] Touch
- [X] USB OTG
- [X] Vibrator
- [X] Wireless LAN
- [X] Wireless backup and restore over curl using FTP, FTPS, HTTP, HTTPS, SCP, SFTP, Telnet, and TFTP
- [X] Interactive FTP/FTPS backup and restore menu in TWRP Terminal
- [X] Magisk installation built in to recovery 

## Charging controls

Open **Advanced > Charging** for native OnePlus bypass on/off, a charging status
report, and **Normal charging / Auto SUPERVOOC**. The same controls are available
with `twrp-charging status`, `twrp-charging bypass-on`, `twrp-charging bypass-off`,
and `twrp-charging auto` from the recovery terminal or a root recovery ADB shell.

Bypass uses the OnePlus PLC driver and requires a wired charger plus permission
from the driver's battery, temperature, and protocol checks. Recovery maintains
an explicitly requested active session across the driver's five-minute user
timeout; it clears its request if the cable is removed or the driver stops
bypass. Enable bypass again after reconnecting. The request is temporary and
is not saved across boots. Disable bypass to return control to normal charging.

The charging service supplies the native driver readiness handshake. Normal
charging removes a bypass request and enables the driver's charging vote;
SUPERVOOC then negotiates automatically with a compatible charger and cable.
The status report labels SUPERVOOC active only when both the wired connection
and VOOC charging state are active and the driver reports the SUPERVOOC protocol.
Adapter capability is not a measurement of actual charging power. Temperature,
current, voltage, authentication, and input-suspend protections stay under driver
control.

This recovery image uses the installed boot kernel and its matching OnePlus
charging modules. Unknown or unavailable driver controls return an error.
Packaging and simulated driver checks do not establish physical charging power;
both modes still require validation while booted into this image.

## Backup compression

When **Enable compression** is selected on the TWRP Backup options page, choose
either **Pigz (gzip, level 9)** or **Zstd (level 11, multithreaded)**. Pigz
remains the default and preserves compatibility with existing compressed `.win`
backups. Zstd archives are detected automatically by this recovery, including
encrypted file-based backups, but require this updated recovery to restore.

ADB backup streams remain gzip for compatibility with TWRP's existing ADB
backup protocol. Both local compression choices remain subject to the recovery
thermal guard.

## Wireless backup and restore with curl

ADB can still be used for command/control while the backup data itself transfers over Wi-Fi from recovery to a Linux or Windows backup server.

Do not add private keys, FTP passwords, personal `known_hosts` files, or `/sdcard/TWRP/ftp.conf` to the device tree.

## Interactive FTP/FTPS menu

The easiest no-ADB backup workflow is the TWRP Terminal menu:

```shell
twrp-ftp-menu
```

Recommended flow:

1. Boot to TWRP.
2. Connect Wi-Fi in TWRP.
3. Create a normal TWRP backup from the TWRP Backup page.
4. Open **Advanced > Terminal**.
5. Run `twrp-ftp-menu`.
6. Add or select an FTP/FTPS server.
7. Use **Test selected server**.
8. Use **Upload newest TWRP backup**.

### Saved FTP server config

The menu stores saved FTP/FTPS server entries in:

```text
/sdcard/TWRP/ftp.conf
```

Format:

```text
name|ftp_or_ftps_directory_url|username|password
```

Example:

```text
home-ftp|ftp://192.168.3.10:21/twrp/|backup_user|backup_password
home-ftps|ftps://192.168.3.10:21/twrp/|backup_user|backup_password
```

Use the FTP path as seen after logging in to the FTP account. For example, if the FTP account is rooted at `~/Downloads` and the real Linux folder is `~/Downloads/twrp`, the FTP URL should usually be:

```text
ftp://192.168.3.10:21/twrp/
```

not:

```text
ftp://192.168.3.10:21/home/user/Downloads/twrp/
```

### Menu options

```text
1) Add FTP/FTPS server to ftp.conf
2) Select FTP/FTPS server from ftp.conf
3) Test selected server
4) Upload newest TWRP backup
5) List remote backup folder
6) Restore backup archive
7) Upload recovery log and network info
8) Show network info
9) Delete ftp.conf
0) Exit
```

### Backup behavior

Option `4` calls `twrp-ftp-backup` using the selected saved server. The default flow uploads the newest local backup folder as a streamed tar archive:

```text
<backup-folder-name>.tar
```

Example target:

```text
ftp://192.168.3.10:21/twrp/2026-07-05--12-23-48_BP2A250605015_release-keys.tar
```

### Restore behavior

Option `6` lists remote backup archives from the selected server directory and lets you pick the archive number to restore. It lists files ending in:

```text
.tar
.tar.gz
.tgz
```

The selected archive keeps its original filename when downloaded to:

```text
/sdcard/TWRP/restore-incoming/
```

Example:

```text
Remote backup archives:

  1) 2026-07-05--12-23-48_BP2A250605015_release-keys.tar

Select archive number to restore, or type m for manual filename:
```

Choosing that archive saves it as:

```text
/sdcard/TWRP/restore-incoming/2026-07-05--12-23-48_BP2A250605015_release-keys.tar
```

The restore helper then extracts the archive into:

```text
/sdcard/TWRP/BACKUPS/<device-serial>/
```

After extraction, open the TWRP Restore page and select the restored backup folder.

### FTP server notes

FTP needs both the control port and passive data ports reachable from TWRP. A successful test should show:

```text
Login successful
Entering Extended Passive Mode
Transfer complete
```

## Command-line FTP/FTPS helpers

Upload the newest local TWRP backup folder:

```shell
twrp-ftp-backup ftp://192.168.3.10:21/twrp/ FTP_USER FTP_PASSWORD
```

Upload a specific local backup folder:

```shell
twrp-ftp-backup --backup 2026-07-05--12-23-48_BP2A250605015_release-keys ftp://192.168.3.10:21/twrp/ FTP_USER FTP_PASSWORD
```

Download and extract a remote backup archive:

```shell
twrp-ftp-restore ftp://192.168.3.10:21/twrp/2026-07-05--12-23-48_BP2A250605015_release-keys.tar FTP_USER FTP_PASSWORD
```

By default, `twrp-ftp-restore` preserves the remote archive filename under `/sdcard/TWRP/restore-incoming/` instead of renaming it to `backup.tar`.

Use `--download-only` to download the archive without extracting it:

```shell
twrp-ftp-restore --download-only ftp://192.168.3.10:21/twrp/backup.tar FTP_USER FTP_PASSWORD
```

Use `--insecure` only for testing FTPS servers with self-signed certificates.

## Experimental SMB mounting

The recovery includes `/system/bin/twrp-smb-mount` for mounting SMB shares under `/mnt/smb`. Once mounted, browse to that path from TWRP File Manager. Credentials are requested at runtime and are not stored in the device tree or on disk.

```shell
twrp-smb-mount mount //192.168.1.25/Backups backups USERNAME WORKGROUP
twrp-smb-mount status
twrp-smb-mount unmount backups
```

Guest shares are also supported:

```shell
twrp-smb-mount guest //192.168.1.25/Public public
```

The utility requires CIFS support from the recovery kernel, either built in or provided by a compatible `cifs.ko`. It reports `cifs-unavailable` without changing other recovery services when that prerequisite is missing. SMB1 is intentionally disabled; automatic negotiation tries SMB 3.1.1, 3.0, then 2.1.

# Controlled kernel-stack helpers

`/system/bin/twrp-flash-kernel` remains the compatibility command for the
existing two-payload workflow.  It delegates to the single authoritative
`/system/bin/twrp-flash-controlled-stack` implementation:

```shell
twrp-flash-kernel --dry-run boot.img system_dlkm.img
```

The controlled-stack helper can validate and flash any selected subset of a
matched `boot`, `vendor_boot`, `system_dlkm`, and `vendor_dlkm` payload set:

```shell
twrp-flash-controlled-stack --dry-run \
  --boot boot.img \
  --vendor-boot vendor_boot.img \
  --system-dlkm system_dlkm.img \
  --vendor-dlkm vendor_dlkm.img
```

Use `--flash` only after the dry run succeeds.  The helper is deliberately
current-slot only; it does not change active-slot metadata.  It verifies the
CPH2747/Canoe/24863 device identity, rejects active Virtual A/B snapshot
updates, checks target capacity and EROFS/ext4 DLKM image format, and backs up
every selected partition by default.  It verifies each backup against its
source, writes `vendor_dlkm`, `system_dlkm`, `vendor_boot`, and finally `boot`,
then verifies every write by SHA-256 read-back.  `system_dlkm_oki` and every
vbmeta partition are intentionally untouched.

The helper validates payload hashes and image structure, but it cannot invent
or change the AVB chain.  Supply only artifacts whose matching AVB relationship
has already been validated.  `--no-backup` exists solely for legacy recovery
diagnostics and is never the normal controlled-stack path.

## Decryption startup

Recovery releases its temporary stock vendor/ODM mounts before starting the
secure-element, OMAPI, Weaver, touch, and health services. The APEX-free build
uses ramdisk libraries without mounting stock vendor again for APEX setup.
`twrp-decrypt-prereqs` checks actual Binder registration with the packaged
`twrp-service-check`; absent services or a missing checker leave prerequisites
failed. Credential submission waits for the prerequisite sequence to finish.
Enter credentials only through the physical recovery GUI.
