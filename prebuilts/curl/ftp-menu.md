# TWRP FTP/FTPS menu

`/system/bin/twrp-ftp-menu` is an interactive TWRP Terminal menu for wireless FTP and FTPS backup workflows when the phone is not connected to ADB.

## Start the menu

1. Boot to TWRP.
2. Connect Wi-Fi in TWRP.
3. Create a normal TWRP backup from the TWRP Backup page.
4. Open **Advanced > Terminal**.
5. Run:

```sh
twrp-ftp-menu
```

## Saved server config

The menu can save FTP and FTPS server entries in:

```text
/sdcard/TWRP/ftp.conf
```

The config file format is:

```text
name|ftp_or_ftps_directory_url|username|password
```

The URL should be the FTP directory as seen after login, not necessarily the server computer's full Linux filesystem path. For example, if the FTP account is rooted at `~/Downloads` and the backup folder is `~/Downloads/twrp`, use `/twrp`:

```text
home-ftp|ftp://192.168.3.10:21/twrp/|backup_user|backup_password
home-ftps|ftps://192.168.3.10:21/twrp/|backup_user|backup_password
```

The menu can create this file for you with **Add FTP/FTPS server to ftp.conf**.

## Important security note

`ftp.conf` stores credentials as plain text. Do not commit it to the device tree and do not bake it into the recovery image.

Recommended practice:

- Use a dedicated FTP account only for TWRP backups.
- Limit that account to the backup folder.
- Prefer `ftps://` when the server supports it.
- Delete `ftp.conf` from the menu when it is no longer needed.

## Menu options

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

The backup option calls `twrp-ftp-backup` using the selected saved server. The default backup flow uploads the newest local TWRP backup folder as `<backup-folder-name>.tar`.

The restore option now lists remote `.tar`, `.tar.gz`, and `.tgz` archives from the selected server directory. Pick the archive number to download and extract it. The downloaded archive keeps its original filename under:

```text
/sdcard/TWRP/restore-incoming/
```

For example, choosing:

```text
2026-07-05--12-23-48_BP2A250605015_release-keys.tar
```

saves the file as:

```text
/sdcard/TWRP/restore-incoming/2026-07-05--12-23-48_BP2A250605015_release-keys.tar
```

instead of renaming it to `backup.tar`.

## FTP server notes

FTP requires both the control port and passive data ports to be reachable from TWRP. A successful test should show login plus a working passive data connection. If listing works and upload fails with `550 Permission denied`, fix the FTP server folder ownership or `write_enable` setting.
