# Optional bundled Magisk payload

Place an official `Magisk.apk` in this directory before building recovery:

```text
prebuilts/magisk/Magisk.apk
```

The recovery device tree packages the payload to:

```text
/system/etc/magisk/Magisk.apk
```

Do not commit third-party Magisk binaries unless you have verified redistribution rights for the exact payload you are adding.

The helper script `twrp-magisk-bundled` will use the packaged payload when present and call `twrp-root-patcher` to patch `boot` or `init_boot` from recovery.
