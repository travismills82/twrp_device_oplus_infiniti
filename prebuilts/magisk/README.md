# Bundled Magisk payload

The tracked `Magisk.apk` is packaged into normal recovery builds at:

```text
/system/etc/magisk/Magisk.apk
```

Current payload: **Magisk 31.1**, package `com.topjohnwu.magisk`, version code
`31100`. The unmodified APK was byte-compared with the official
[v31.1 release APK](https://github.com/topjohnwu/Magisk/releases/download/v31.1/Magisk-v31.1.apk).

SHA-256: `89cefac0a318afa39fb3880c45c87b036c05bc1ebf02a7a715b7f8d7c26ac6e7`

Magisk is distributed under the included [GNU GPL version 3](LICENSE).
Corresponding source and build instructions for this exact version are
available from [the upstream v31.1 source tree](https://github.com/topjohnwu/Magisk/tree/v31.1).
Upstream notices within the APK are preserved. The retired duplicate
`Magisk-v31.0.apk` is no longer bundled in the source tree; builds use only
the stable `Magisk.apk` filename.

Set `WITH_BUNDLED_MAGISK=false` only when intentionally producing an
unbundled diagnostic recovery image. The source payload is:

```text
prebuilts/magisk/Magisk.apk
```

Do not commit third-party Magisk binaries unless you have verified redistribution rights for the exact payload you are adding.

The helper script `twrp-magisk-bundled` will use the packaged payload when present and call `twrp-root-patcher` to patch `boot` or `init_boot` from recovery.
