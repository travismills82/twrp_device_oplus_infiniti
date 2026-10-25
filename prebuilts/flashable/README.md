# TWRP flashable package

The GitHub Actions workflow builds the flashable ZIP from scratch by running:

```shell
prebuilts/flashable/build-twrp-installer.sh \
    recovery.img \
    TWRP-3.7.1-16-infiniti.zip \
    "TWRP 3.7.1-16" \
    "OnePlus 15 (infiniti)"
```

The generated installer:

- displays the TWRP version and target device;
- extracts the newly built `recovery.img`;
- flashes it only to `recovery_a`;
- leaves the active slot unchanged;
- requires TWRP and OnePlus 15 boot project ID 24831 or 24863;
- validates the packaged SHA-256 before writing;
- requires `recovery_a` to be exactly 100 MiB;
- verifies the complete `recovery_a` readback after the write; and
- checks generated installer text for inherited recovery branding.

`recovery_b` is intentionally not touched. Official A/B updates write its
recovery image as part of a matching boot and AVB set; overwriting it can make
the newly updated slot unbootable.

The builder also compares the ZIP payload against the input image. The build
workflow scans the uncompressed recovery ramdisk separately. Test installer
behavior without accessing any physical block device:

```shell
python3 scripts/test-recovery-installer.py /path/to/TWRP-infiniti.zip
```

The package source is generated programmatically so no third-party recovery installer payload is reused.
