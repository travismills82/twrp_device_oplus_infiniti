# TWRP device tree for OPLUS infiniti

## Supported devices

- OnePlus 15 (CN)

## Build it yourself?

```shell
mkdir twrp && cd twrp
repo init --depth=1 -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp.git -b twrp-16.0
repo sync
git clone --depth=1 https://github.com/koaaN/twrp_device_oplus_infiniti device/oplus/infiniti
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
- [O] Decryption
- [X] Fastbootd
- [O] Flashing
- [O] MTP
- [O] Sideload
- [O] Touch
- [O] USB OTG
- [X] Vibrator

## To use it:

```shell
fastboot flash recovery recovery.img
```

or

```shell
fastboot flash recovery_a recovery.img
fastboot flash recovery_b recovery.img
```
