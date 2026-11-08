# Modern recovery UI and native Wi-Fi — preview

This locally built pre-release contains the OxygenOS-style red/black TWRP
dashboard, shared red controls, red progress/unlock styling, native Wi-Fi list
and password flow, and bundled Magisk 31.1. It does not replace the previous
stable release as Latest.

## Known issue

**Intermittent GPU redraw loss remains unresolved.** Hardware GLES composition
runs on the tested phone, but some live frames still lose status characters or
panel fills. Font-cache lifetime and GPU-owned vertex-buffer repairs are
included; passing short/off-screen tests does not establish a complete fix.
This is a test build, not a stable-GPU or full recovery qualification claim.

When no operation is running, software rendering can be selected for the current
boot from recovery ADB:

```shell
adb shell 'setprop twrp.gpu.enable 0; twrp changepage=main2'
```

This diagnostic property is temporary; normal startup uses the configured GPU
path again after a reboot. Do not change pages during a backup, restore or flash.

## Changes

- Native dashboard with genuine slot, decryption, storage, charging and Wi-Fi
  state; no simulated success indicators. Cellular bars are intentionally hidden.
- Red shared controls, PIN/keyboard confirmation, splash, file-manager accents,
  loading bars and continuous unlock swipe; screen timeout remains enabled.
- Modern WLAN scan list with measured dBm, actual count/status and red scrolling.
  A secured-row tap opens a focused, masked password keyboard. Cancel clears the
  entered password. Existing network diagnostics remain under Tools.
- Successful Wi-Fi profiles are remembered under `/data/twrp/wifi`, outside
  user-0 CE storage, and reconnected automatically. `/data` must still mount;
  metadata-decryption failure or formatting can make profiles unavailable.
- Font-cache use-after-free/path-allocation repair, GPU vertex ownership
  hardening, GUI-thread WLAN row updates and synchronized network logs.
- Pinned XML recovery source and tracked incremental theme/library dependencies,
  with regression tests and repeatable recovery-patch application.

## Validation and limits

The normal local `recoveryimage` toolchain completed. All 40 recovery patches and
the external series apply cleanly; repeat application leaves the source
byte-identical. 119 Python cases, native/sanitizer fixtures, and nine installer
tests against disposable regular files pass. The packed XML/assets, native
recovery executable, graphics library, bundled Magisk, image budget and AVB
footer were checked. The installer also passed its recovery-side `--dry-run`
preflight with no partition writes.

The exact image was cold-tested only on the connected OnePlus 15 running ColorOS
17 with kernel `6.12.116-android16-6-o-gc2e2f95d3c3c-4k`. User-0 decryption,
ADB/MTP, saved Wi-Fi reconnection, scanning, three native row/keyboard/Back
cycles, masked test input/cancel clearing, Tools routing and internet connectivity
passed. Full image and graphics-library readbacks matched. Saved Samsung-style
right-side Back navigation was preserved. Off-screen GLES stress passed, but
the separate live visual defect above still reproduced. This does not freshly
qualify other firmware/kernels, backup/restore, OTG, OTA or long-duration use.

Only the explicitly approved `recovery_a` was written during those earlier
tests; `recovery_b`, `boot_a`, `vendor_boot_a`, the active slot and both fstabs
were unchanged. Publication does not perform another flash or GitHub build.
No radio stack, modem/NV write, EDL feature or partition manager is included.

## Artifacts

The release publishes the already-tested image and slot-A-only installer ZIP,
not a newly rebuilt or untested replacement. The ZIP's embedded recovery image
is identical to the standalone image. The installer deliberately preserves
`recovery_b` and verifies the `recovery_a` readback.

| File | SHA-256 |
| --- | --- |
| `TWRP-infiniti-OxygenOS-modern-WiFi-test-20261107.img` | `42286f1cf94ffefa9cbea6259db518cc372a140709cc01ae5d21d9de95f5d7f8` |
| `TWRP-infiniti-OxygenOS-modern-WiFi-test-20261107.zip` | `78575bd8a5a554de023210f22558c2441df63a7350e4e54d42d5453b1fd91627` |

The image is 104857600 bytes including normal AVB full-partition padding, with
8269824 bytes of pre-footer payload growth room. Verify `SHA256SUMS` after
downloading. Keep a verified rollback image and a working bootloader recovery
path. Do not overwrite an official OTA's inactive-slot recovery with this image.

Further details: [GPU implementation/limits](../RECOVERY_GPU.md),
[native Wi-Fi](../MODERN_WIFI.md), [saved profiles](../WIFI_PERSISTENCE.md).
