# Bundled Magisk payload

The tracked `Magisk.apk` is packaged into normal recovery builds at:

```text
/system/etc/magisk/Magisk.apk
```

Set `WITH_BUNDLED_MAGISK=false` only when intentionally producing an
unbundled diagnostic recovery image. The source payload is:

```text
prebuilts/magisk/Magisk.apk
```

Do not commit third-party Magisk binaries unless you have verified redistribution rights for the exact payload you are adding.

The helper script `twrp-magisk-bundled` will use the packaged payload when present and call `twrp-root-patcher` to patch `boot` or `init_boot` from recovery.
