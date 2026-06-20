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
- flashes it to both `recovery_a` and `recovery_b`;
- leaves the active slot unchanged;
- validates that both recovery partitions exist;
- checks the image against the partition size when `blockdev` is available; and
- rejects OrangeFox or OFRP branding in the recovery image or installer files.

The package source is generated programmatically so no third-party recovery installer payload is reused.
