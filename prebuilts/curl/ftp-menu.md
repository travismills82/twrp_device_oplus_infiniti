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

Example:

```text
home-ftp|ftp://192.168.3.10/twrp-backups|backup_user|backup_password
home-ftps|ftps://192.168.3.10/twrp-backups|backup_user|backup_password
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

The backup option calls `twrp-ftp-backup` using the selected saved server. The restore option calls `twrp-ftp-restore` using the selected saved server.
