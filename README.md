# TWRP device tree for OPLUS infiniti

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
