# Building TWRP for OnePlus 15

Use the TWRP-Test Android 16 manifest and clone this device tree to device/oplus/infiniti.

After each fresh source sync, run:

    device/oplus/infiniti/scripts/apply-recovery-patches.sh

Then build with the normal TWRP commands:

    source build/envsetup.sh
    lunch twrp_infiniti
    make recoveryimage

The recovery patch helper is idempotent. It updates the WLAN implementation to use the network identifier returned by wpa_supplicant, validates connection commands, waits for DHCP, and uses the packaged ping command for connectivity checks. It also applies the recovery-only update-engine repair that clears a stale failed Virtual A/B update immediately before a replacement signed OTA is sideloaded; it does not change Android's live-update behavior.

The resulting image is written to out/target/product/infiniti/recovery.img.

Validate the charging controller and decryption startup from the source root:

    python3 device/oplus/infiniti/scripts/test-charging.py
    python3 device/oplus/infiniti/scripts/test-decrypt-readiness.py

These tests use a temporary simulated driver and do not connect to a phone. After building,
verify the AVB footer and unpack the image to check `twres/portrait.xml`, the
`op15charging` GUI action, `system/bin/twrp-charging`, and its init service.
Also verify `system/bin/twrp-service-check`, the decryption prerequisite helper,
and the disabled HAL definitions with their `twrp.fstab.ready=1` startup gate.
On-device validation must confirm Binder readiness, successful PIN entry through
the physical GUI, and absence of the vendor unmount error after a fresh boot.
