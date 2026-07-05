# TWRP device tree for ONEPLUS infiniti

## Supported devices

- OnePlus 15

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

## Wireless backup and restore with curl

The recovery includes:

```text
/system/bin/curl
/system/bin/twrp-curl
/system/bin/twrp-sftp
/system/bin/twrp-ftp-menu
/system/bin/twrp-ftp-backup
/system/bin/twrp-ftp-restore
```

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

For a Linux `vsftpd` server, useful settings include:

```conf
local_enable=YES
write_enable=YES
local_umask=022
pasv_enable=YES
pasv_min_port=40000
pasv_max_port=40100
```

Open the firewall for the FTP control port and passive range:

```shell
sudo ufw allow 21/tcp
sudo ufw allow 40000:40100/tcp
```

If listing works but upload fails with `550 Permission denied`, fix the backup folder ownership and confirm `write_enable=YES` in the FTP server config.

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

## Flash recovery

```shell
fastboot flash recovery recovery.img
```

or

```shell
fastboot flash recovery_a recovery.img
fastboot flash recovery_b recovery.img
```
