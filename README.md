# TWRP device tree for ONEPLUS infiniti

## Supported devices

- OnePlus 15

## Build it yourself?

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

If there is no error, recovery.img will be found in `out/target/product/infiniti/recovery.img`

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

## Wireless backup and restore with curl / SFTP

The recovery includes `/system/bin/curl`, `/system/bin/twrp-curl`, and `/system/bin/twrp-sftp` for wireless network file transfer. SFTP is recommended for moving backups because it encrypts the transfer and verifies the SSH server through `known_hosts`.

ADB can still be used for command/control while the backup data itself transfers over Wi-Fi from recovery to the Linux or Windows backup server.

Credentials and host keys should be staged only in `/tmp/twrp-network`. Do not add private keys, passwords, or personal `known_hosts` files to the device tree.

### Linux backup server setup

From the Linux computer that will receive or provide backups, create a temporary SSH key and authorize it:

```shell
ssh-keygen -t rsa -b 3072 -m PEM -N '' -f ~/Downloads/twrp-sftp-id_rsa
mkdir -p ~/.ssh
chmod 0700 ~/.ssh
cat ~/Downloads/twrp-sftp-id_rsa.pub >> ~/.ssh/authorized_keys
chmod 0600 ~/.ssh/authorized_keys
mkdir -p ~/twrp-backups
```

Create and verify a `known_hosts` file. Replace `192.168.3.10` with the Linux backup server address:

```shell
ssh-keyscan -t ed25519 192.168.3.10 > ~/Downloads/twrp-known_hosts
ssh-keygen -lf ~/Downloads/twrp-known_hosts -E sha256
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

The SHA256 fingerprints should match.

Push the temporary credentials into recovery:

```shell
adb shell 'mkdir -p /tmp/twrp-network && chmod 0700 /tmp/twrp-network'
adb push ~/Downloads/twrp-known_hosts /tmp/twrp-network/known_hosts
adb push ~/Downloads/twrp-sftp-id_rsa /tmp/twrp-network/id_rsa
adb push ~/Downloads/twrp-sftp-id_rsa.pub /tmp/twrp-network/id_rsa.pub
adb shell 'chmod 0600 /tmp/twrp-network/known_hosts /tmp/twrp-network/id_rsa && chmod 0644 /tmp/twrp-network/id_rsa.pub'
```

### Windows backup server setup

Windows 10, Windows 11, and current Windows Server releases include OpenSSH support. Run PowerShell as Administrator on the Windows computer that will receive or provide backups:

```powershell
# Install OpenSSH Server if it is not already installed
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH*'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start SSH and enable it at boot
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Open the Windows firewall for SSH if setup did not already create the rule
if (!(Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
}
```

Create a backup folder and note the Windows IP address:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\twrp-backups"
ipconfig
whoami
```

Create a temporary SSH key for TWRP and authorize it for the Windows user. Use a normal non-administrator Windows account when possible:

```powershell
ssh-keygen -t rsa -b 3072 -m PEM -N "" -f "$env:USERPROFILE\Downloads\twrp-sftp-id_rsa"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh"
Get-Content "$env:USERPROFILE\Downloads\twrp-sftp-id_rsa.pub" | Add-Content "$env:USERPROFILE\.ssh\authorized_keys"

icacls "$env:USERPROFILE\.ssh" /inheritance:r /grant "$env:USERNAME:(OI)(CI)F"
icacls "$env:USERPROFILE\.ssh\authorized_keys" /inheritance:r /grant "$env:USERNAME:F"
```

Create and verify a `known_hosts` file. Replace `192.168.3.20` with the Windows backup server address:

```powershell
ssh-keyscan -t ed25519 192.168.3.20 > "$env:USERPROFILE\Downloads\twrp-known_hosts"
ssh-keygen -lf "$env:USERPROFILE\Downloads\twrp-known_hosts" -E sha256
ssh-keygen -lf "C:\ProgramData\ssh\ssh_host_ed25519_key.pub" -E sha256
```

The SHA256 fingerprints should match.

Push the temporary credentials into recovery from PowerShell:

```powershell
adb shell "mkdir -p /tmp/twrp-network && chmod 0700 /tmp/twrp-network"
adb push "$env:USERPROFILE\Downloads\twrp-known_hosts" /tmp/twrp-network/known_hosts
adb push "$env:USERPROFILE\Downloads\twrp-sftp-id_rsa" /tmp/twrp-network/id_rsa
adb push "$env:USERPROFILE\Downloads\twrp-sftp-id_rsa.pub" /tmp/twrp-network/id_rsa.pub
adb shell "chmod 0600 /tmp/twrp-network/known_hosts /tmp/twrp-network/id_rsa && chmod 0644 /tmp/twrp-network/id_rsa.pub"
```

Windows OpenSSH SFTP paths normally use this format:

```text
/C:/Users/WINDOWS_USER/twrp-backups/backup.tar
```

### Upload a TWRP backup wirelessly to a Linux SFTP server

Create the backup normally in TWRP first. Then upload the newest backup folder as a streamed tar archive so a second full local copy is not required:

```shell
adb shell '
set -e
SERIAL="$(getprop ro.serialno)"
BACKUP_ROOT="/sdcard/TWRP/BACKUPS/$SERIAL"
BACKUP_NAME="$(ls -1t "$BACKUP_ROOT" | head -n 1)"

cd "$BACKUP_ROOT"
tar -cf - "$BACKUP_NAME" | \
  /system/bin/twrp-curl \
    --fail --show-error \
    --knownhosts /tmp/twrp-network/known_hosts \
    --key /tmp/twrp-network/id_rsa \
    --pubkey /tmp/twrp-network/id_rsa.pub \
    --user travis: \
    --upload-file - \
    "sftp://192.168.3.10:22/home/travis/twrp-backups/${BACKUP_NAME}.tar"
'
```

Change the username, host, and remote directory for your own Linux backup server.

### Upload a TWRP backup wirelessly to a Windows SFTP server

Create the backup normally in TWRP first. Replace `WINDOWS_USER` and `192.168.3.20` with the Windows username and IP address:

```shell
adb shell '
set -e
SERIAL="$(getprop ro.serialno)"
BACKUP_ROOT="/sdcard/TWRP/BACKUPS/$SERIAL"
BACKUP_NAME="$(ls -1t "$BACKUP_ROOT" | head -n 1)"

cd "$BACKUP_ROOT"
tar -cf - "$BACKUP_NAME" | \
  /system/bin/twrp-curl \
    --fail --show-error \
    --knownhosts /tmp/twrp-network/known_hosts \
    --key /tmp/twrp-network/id_rsa \
    --pubkey /tmp/twrp-network/id_rsa.pub \
    --user WINDOWS_USER: \
    --upload-file - \
    "sftp://192.168.3.20:22/C:/Users/WINDOWS_USER/twrp-backups/${BACKUP_NAME}.tar"
'
```

### Download and restore a TWRP backup from Linux SFTP

Download the archive back to internal storage:

```shell
adb shell '
set -e
mkdir -p /sdcard/TWRP/restore-incoming

/system/bin/twrp-curl \
  --fail --show-error \
  --knownhosts /tmp/twrp-network/known_hosts \
  --key /tmp/twrp-network/id_rsa \
  --pubkey /tmp/twrp-network/id_rsa.pub \
  --user travis: \
  --output /sdcard/TWRP/restore-incoming/backup.tar \
  "sftp://192.168.3.10:22/home/travis/twrp-backups/backup.tar"
'
```

Extract it into the TWRP backup folder for the current device serial:

```shell
adb shell '
set -e
SERIAL="$(getprop ro.serialno)"
RESTORE_ROOT="/sdcard/TWRP/BACKUPS/$SERIAL"
mkdir -p "$RESTORE_ROOT"
tar -C "$RESTORE_ROOT" -xf /sdcard/TWRP/restore-incoming/backup.tar
ls -la "$RESTORE_ROOT"
'
```

After extraction, use the TWRP Restore page and select the restored backup folder.

### Download and restore a TWRP backup from Windows SFTP

Download the archive from the Windows backup folder. Replace `WINDOWS_USER` and `192.168.3.20` with the Windows username and IP address:

```shell
adb shell '
set -e
mkdir -p /sdcard/TWRP/restore-incoming

/system/bin/twrp-curl \
  --fail --show-error \
  --knownhosts /tmp/twrp-network/known_hosts \
  --key /tmp/twrp-network/id_rsa \
  --pubkey /tmp/twrp-network/id_rsa.pub \
  --user WINDOWS_USER: \
  --output /sdcard/TWRP/restore-incoming/backup.tar \
  "sftp://192.168.3.20:22/C:/Users/WINDOWS_USER/twrp-backups/backup.tar"
'
```

Extract it into the TWRP backup folder for the current device serial:

```shell
adb shell '
set -e
SERIAL="$(getprop ro.serialno)"
RESTORE_ROOT="/sdcard/TWRP/BACKUPS/$SERIAL"
mkdir -p "$RESTORE_ROOT"
tar -C "$RESTORE_ROOT" -xf /sdcard/TWRP/restore-incoming/backup.tar
ls -la "$RESTORE_ROOT"
'
```

After extraction, use the TWRP Restore page and select the restored backup folder.

### Quick file upload or download

Use `twrp-sftp` for individual files such as logs, ZIPs, images, or a single backup archive:

```shell
# Download a file into recovery from Linux
adb shell 'twrp-sftp download travis@192.168.3.10:/home/travis/file.zip /sdcard/Download/file.zip'

# Download a file into recovery from Windows
adb shell 'twrp-sftp download WINDOWS_USER@192.168.3.20:/C:/Users/WINDOWS_USER/twrp-backups/file.zip /sdcard/Download/file.zip'

# Upload the current recovery log to Linux
adb shell 'twrp-sftp upload /tmp/recovery.log travis@192.168.3.10:/home/travis/recovery.log'

# Upload the current recovery log to Windows
adb shell 'twrp-sftp upload /tmp/recovery.log WINDOWS_USER@192.168.3.20:/C:/Users/WINDOWS_USER/twrp-backups/recovery.log'

# List a Linux remote directory
adb shell 'twrp-sftp list travis@192.168.3.10:/home/travis/twrp-backups/'

# List a Windows remote directory
adb shell 'twrp-sftp list WINDOWS_USER@192.168.3.20:/C:/Users/WINDOWS_USER/twrp-backups/'
```

If you need a custom port or key path:

```shell
adb shell 'twrp-sftp --port 2222 --key /tmp/twrp-network/id_rsa --pubkey /tmp/twrp-network/id_rsa.pub list travis@192.168.3.10:/home/travis/'
```

## Experimental SMB mounting

The recovery includes `/system/bin/twrp-smb-mount` for mounting SMB shares under `/mnt/smb`. Once mounted, browse to that path from TWRP File Manager. Credentials are requested at runtime and are not stored in the device tree or on disk.

```shell
twrp-smb-mount mount //192.168.1.25/Backups backups travis WORKGROUP
twrp-smb-mount status
twrp-smb-mount unmount backups
```

Guest shares are also supported:

```shell
twrp-smb-mount guest //192.168.1.25/Public public
```

The utility requires CIFS support from the recovery kernel, either built in or provided by a compatible `cifs.ko`. It reports `cifs-unavailable` without changing other recovery services when that prerequisite is missing. SMB1 is intentionally disabled; automatic negotiation tries SMB 3.1.1, 3.0, then 2.1.

## To use it:

```shell
fastboot flash recovery recovery.img
```

or

```shell
fastboot flash recovery_a recovery.img
fastboot flash recovery_b recovery.img
```
