# Building TWRP for OnePlus 15

Use the TWRP-Test Android 16 manifest and clone this device tree to device/oplus/infiniti.

After each fresh source sync, run:

    device/oplus/infiniti/scripts/apply-recovery-patches.sh

Then build with the normal TWRP commands:

    source build/envsetup.sh
    lunch twrp_infiniti
    make recoveryimage

The recovery patch helper is idempotent. It updates the WLAN implementation to use the network identifier returned by wpa_supplicant, validates connection commands, waits for DHCP, and uses the packaged ping command for connectivity checks.

The resulting image is written to out/target/product/infiniti/recovery.img.
