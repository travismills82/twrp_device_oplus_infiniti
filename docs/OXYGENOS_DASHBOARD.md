# Experimental OxygenOS-style native recovery dashboard

Developed on `experiment/oxygenos-twrp-ui`, based on `ed9b414`, then prepared
for the owner's requested push to `twrp-16.0` and preview release. Magisk 31.1
was separately committed as `bdc8ef4`. The sections below retain the historical
build/test sequence; earlier references to uncommitted work or no publication
describe those test stages, not the later publication request. Current release
scope and known GPU defect: [preview release notes](releases/2026-11-07-modern-ui-wifi.md).
Only the separately approved `recovery_a` was written during physical tests;
publication performs no additional device flash or GitHub build.

## Design and real actions

The supplied 941×1672 design and TWRP's **1080×1920 logical theme** have the
same aspect ratio. All groups fit on one page without scrolling, cropping or
a GUI-engine replacement. Main targets are 466×132, 230×146, 300–466×104–106,
and 224–250×88 logical pixels; adjacent targets do not overlap. TWRP performs
the existing framebuffer scaling. Icons retain their aspect ratio.

| Reference component | Native implementation and behavior |
| --- | --- |
| Black status bar | Shared `oxygenos_status` XML template: real clock and CPU temperature use the same white font/size, with a small thermometer. Existing Wi-Fi resource at x=800,y=2 appears only when `tw_wifi_connected=1`. Visible glyphs are vertically aligned, accounting for font ascent and transparent image padding. Battery icon ends at x=1000, inset from the rounded corner. No cellular glyph or modem startup. |
| Header and red sweep | Separate small transparent `oxy_logo`/`oxy_wave` resources, real `%tw_version%`, existing RobotoCondensed font. No reference screenshot is packaged. |
| Three pills | Read-only native `tw_op15_dashboard_*` values: existing active-slot/crypto/user-0 flags plus bounded kernel mount metadata. Unknown/unmounted/locked states are not green successes. |
| Flash & Data | Install copies `queueclear → install`; Wipe, Backup and Restore copy the existing main-page actions. Existing selections, warnings, confirmation sliders and backend safety remain untouched. |
| Device & System | Existing `mount`, `settings`, `advanced`, `reboot` pages. |
| Network & Tools | Six tiles: existing WLAN, File Manager, Terminal, FTP, ADB Sideload and Charging. Charging copies the Advanced `op15_charging` page action; opening it does not change charging mode. FTP retains `editfile /system/bin/twrp-ftp-menu → terminalcommand`. Wi-Fi icon is white when disconnected and green when connected, using mutually exclusive `tw_wifi_connected` conditions. WLAN attribution subtitle is removed from the screen only; controls and source attribution remain. Sideload still requires its normal confirmation slider. |
| Quick actions | Copies complete existing reboot list-item action chains, including capability conditions and `reboot_system_routine` / `rebootcheck`; never calls the reboot handler directly. |
| Footer / navigation | Battery/CPU/Last Backup stats removed. Classic Back, Home and Logs icons now have separate 192×128 touch targets at the bottom, including inside the Logs/Menu overlay. Back/Menu dismiss logs; Home dismisses them and returns home. Sections are shifted down with balanced spacing, without overlapping navigation. Hardware Home/Back, power/backlight toggle and screenshot chord remain. Original subpage navigation/modals are retained. |

The layout and labels live in `assets/twrp-theme/oxygenos/dashboard.json`.
`tools/patch_oxygenos_dashboard.py` generates actual TWRP elements and copies
actions from the installed source theme. Original main-page actions are read
from pinned Git source at build time: no Classic shortcut or Classic fallback
page is packaged. The startup `main → clear_vars → main2` lifecycle is intact.
Shared controls retain their handlers with charcoal/red resources. Paired action
buttons are 468×112 (large variants 468×160), anchored at x=36/576 for a 72-pixel
center gap and symmetric margins. Full-width actions are 1008×112. Confirmation
sliders and large navigation targets retain their previous geometry. Every menu
header now uses the same 96×96 logo at x=56,y=106 as home; the launch splash
intentionally keeps its larger logo. File Manager separators/scroll accents and
the folder action are red, and document icons are neutral white.
sliders (including lock), splash, highlights and keyboard accent use red.
Subpage layouts, translations and OLED-black page/status/nav backgrounds remain.
The new group/status labels use the English design text.

There is no LVGL, web/Android app, opaque full-screen background, invisible
screenshot hot-zone map, fake scroll indicator or auto-executed operation.

## Status correctness and threading

Patch `0034-oxygenos-dashboard-readonly-status.patch` adds a small read-only
DataManager provider and its policy header. It does not modify decryption.

- Before `twrp.fstab.ready=1`, or while `tw_busy` is set, crypto/storage report
  Unknown/Unavailable. Missing crypto flags fail closed.
- A valid `/data` mount must appear in kernel `mountinfo` as a block-backed
  F2FS/ext4 filesystem. A tmpfs placeholder or a `/data_mirror` mount is not data.
- FBE requires BOTH TWRP's decrypted state and `twrp.user.0.decrypt=1` before
  reporting Decrypted/usable internal storage. DE-only decryption is insufficient.
- An unmounted data filesystem never reports Decrypted or mounted storage.
- The mount/unlock snapshot refreshes at most once per second. It reports
  TWRP state, not filesystem integrity or verified backup/restore readiness.
- TWRP caches visibility conditions. A tiny native GUI-loop tick notifies only
  changed storage/battery-validity snapshots and requests repaint. It never
  queues a GUI action, so startup/decrypt retain the existing action thread.
- There is no new worker, GUI action, shell command, DNS query, media-directory
  scan, credential input, property write or `/data` file operation in the
  status provider. CPU reads reuse the existing thermal implementation.
- Unknown/missing CPU/battery readings display Unavailable, not fabricated 0 °C
  or a percentage copied from the design.

## Source and build reproducibility

The fresh upstream recovery branch moved to a different GUI2-only codebase.
The existing OP15 patch series targets XML recovery base
`6bd8134ec8ff4cb29eb25797cbb20796f8455204`. The experiment explicitly pins that
base via `config/recovery-source-revision.txt` and
`scripts/select-recovery-source.sh`. Selection refuses to change a dirty
different checkout; it never resets or cleans user edits.

The previously developed Wi-Fi profile/auto-connect and cellular-indicator
changes (`0031`–`0033`) were salvaged from the earlier feature checkout and
preserved as uncommitted changes on this stable-based experiment. They are
not a claim that cellular connectivity works. No radio startup is added.
The cold build exposed a misplaced saved-profile block inside DHCP polling.
Its preserved patch now saves once after successful authentication, before
polling DHCP; regression checks enforce that ordering and the compiler's
warnings-as-errors policy remains enabled.

The fresh upstream vold removed its old temporary-directory code. The patch
runner recognizes the exact replacement's no-persistent-key-upgrade guards
instead of editing crypto code to reintroduce that path. Unrecognized code
still fails validation. Existing patch syntax is checked even when superseded.

The same upstream vold removed the startup `copySqliteDb()` API. It already
calls `syncKeystoreDb()` from its decrypt backend before synthetic-password
key lookup. Patch `0035` removes only the obsolete recovery startup call;
`Decrypt_Page` and all vold source remain unchanged. The patch runner and tests
require the replacement API/ownership, so this cannot silently pair with an
older backend that depended on the startup copy. Physical decrypt confirmation
is still required before this experiment can be qualified.

The cold build also exposed a public-header dependency omission in libsnapshot:
`cow_reader.h` includes an update-engine header without exporting that include
path. `patches/system-core/0002-libsnapshot-export-update-engine-headers.patch`
exports its already declared header dependency. No snapshot code or OTA safety
behavior is disabled or changed.

From the Android build root:

```sh
bash device/oplus/infiniti/scripts/select-recovery-source.sh
bash device/oplus/infiniti/scripts/apply-recovery-patches.sh
bash device/oplus/infiniti/scripts/validate-oxygenos-ui.sh .
source build/envsetup.sh
export ALLOW_MISSING_DEPENDENCIES=true  # same as the project's normal workflow
lunch twrp_infiniti
m -j4 recoveryimage
python3 device/oplus/infiniti/tools/verify_oxygenos_image.py \
  out/target/product/infiniti/recovery.img --root .
python3 device/oplus/infiniti/scripts/verify-gpu-image.py \
  out/target/product/infiniti/recovery.img --root .
```

`apply-recovery-patches.sh` installs all existing patches, applies the Advanced
helper transformer, installs the OxygenOS resources and runs the dashboard
contracts. The existing later Magisk/Charging transformer remains idempotent.
Patch `0036` adds Soong dependencies for theme inputs, and the device makefile
connects the staged XML to the recovery ramdisk packaging timestamp. This fixes
an observed incremental-build failure where source XML changed but an old theme
remained inside the image. Verification compares the actual packed theme.
The experimental workflow selects the supported source and runs the same
dashboard checks. It has not been triggered or published by this task.

The ordinary build requires no new Python packages. Optional artwork regeneration
and host fixture rendering use Pillow:

```sh
python3 device/oplus/infiniti/tools/generate_oxygenos_assets.py /tmp/oxy-assets
python3 device/oplus/infiniti/tools/render_oxygenos_dashboard.py \
  bootable/recovery /tmp/oxygenos-fixture.png --state unknown
```

These previews render the generated XML/resources with **synthetic fixture
values**. They are not screenshots or proof of physical touch/decryption.

## Validation and image budget

The source validator covers actual native actions, reboot confirmation chains,
large non-overlapping hit rectangles, all image checksums/dimensions/RGBA alpha,
resource/page/variable uniqueness, native status fixtures, read-only integration,
the upstream-vold guard and repeat theme application. Existing OTA, backup,
decryption, Wi-Fi, charging and GPU tests remain enabled.

Fresh clean upstream clones must receive the entire sorted patch series twice
without byte changes or `git diff --check` failures. The image verifier checks
AVB signing/footer geometry, packaged pages/status provider, every actual PNG,
retained recovery helpers and exact byte counts. GPU packaging verification
checks the compiled renderer and retained active-slot loader separately.
On this source branch `libguitwrp` is static: the packed recovery executable
must exactly match its built stripped ELF and contain the dashboard provider
and live-condition notifier. The GPU renderer is a separate `libminuitwrp.so`
and is independently byte-compared by the existing checker.
The packed Magisk APK must also be byte-identical to the source prebuilt; a
source APK replacement requires a new ramdisk build and verification.

There are 85 independent compact PNGs, **267,071 bytes** total before ramdisk
compression, less than 16 MiB decoded. No new fonts or external theme pack is added.
The requested twelve-frame outlined red progress style has an explicit 288 KiB
total artwork budget; the per-image 64 KiB and decoded 16 MiB limits remain.
Both fstab files, `twrp.flags`, firmware/modules, AVB policy and the physical
`0x6400000` (104,857,600-byte) recovery limit are not changed by the UI work.

The normal AVB format pads the final file to the full physical partition.
Therefore final-file slack can be zero even when the kernel/ramdisk payload has
several MiB of growth capacity. Report both exact file slack and AVB-calculated
payload headroom; do not shrink the partition size or remove the AVB footer
merely to claim a smaller file. The final build report records measured values.

### Historical first candidate, 2026-11-07 (superseded)

Build and packed-image verification **PASS**, including the user's Magisk 31.1
update. Image SHA-256:
`997979e0d0f942d5eb56feccc23790559a460ec12f925e3dc22066709d4d7cbb`.

- Final AVB-footed image: **104,857,600 bytes**; unchanged physical limit:
  **104,857,600 bytes**; final-file slack: **0 bytes** (normal AVB padding).
- Original pre-footer payload: **96,399,360 bytes**; AVB-calculated maximum:
  **104,787,968 bytes**; payload growth headroom: **8,388,608 bytes (8 MiB)**.
- All 35 recovery patches and external patches apply cleanly to fresh source
  clones; repeat application leaves all file hashes identical.
- All **94** host/source Python cases, native status and backup safety fixtures,
  XML/resource/action checks, AVB verification, packed executable/PNG/APK checks,
  packed GPU verification, and **9** regular-file installer tests pass.
- Actual image: `out/target/product/infiniti/recovery.img`. Copy, test ZIP,
  checksums, complete build logs, previews, manifest and source backups are in
  `/home/travis/Android/twrp-oxygenos-artifacts-20261107.zIdLEJ/`.
- Only Magisk was committed (`bdc8ef4`); UI changes remain uncommitted on the
  experiment. Local default `twrp-16.0` now also contains that Magisk-only commit;
  the remote remains `ed9b414`. No push or release.

This first dashboard candidate was successfully flashed to `recovery_a` under
the later explicit test approval. It is superseded by the red-theme revisions,
which were first previewed through a RAM-only `/twres` bind. The later approved
cold-boot test below supersedes those RAM-only results.

### Red-theme revisions and physical evidence

The red-v2 packed image passed source, AVB, asset, ELF, Magisk and GPU packaging
checks: SHA-256
`cc331006801ee4010d1eb43864650bce4bfb0aef614eea6345f01e0f79cf060a`.
It has 8,294,400 bytes of AVB-calculated payload growth capacity; the padded
final file remains 104,857,600 bytes. Later revisions enlarge the CPU reading to
the clock's font, add the thermometer, align visible status glyphs, reposition
sections, keep navigation visible in logs, narrow shared buttons, finish File
Manager red accents and unify menu logos; consult the latest image report/hash.

All 37 recovery patches and external series applied twice to fresh source
clones without byte changes. The latest full host/source suite covers 108 Python
cases plus native fixtures. Original fstab files, `twrp.flags` and vold source
are unchanged. Re-run these checks after any later source edit.

On the connected phone the first image booted and decrypted user 0; internal
F2FS/media, saved-network reconnection, WLAN-bound internet, MTP/ADB and real
Adreno GLES rendering worked. GPU/IOMMU fault counters were zero. All thirteen original
primary menu routes and Home were exercised without confirming an install/wipe/restore slider.
The Restore PIN warning is intentional original behavior, not a decrypt failure.
The added Charging tile was separately tapped and opened `op15_charging`, then
returned home, without selecting a charging-mode action.
Its lightning icon is white unless a bounded, read-only battery `status` query
reports exactly `Charging`. Unknown, missing, full, discharging and not-charging
states do not turn it green. A one-second native cache/GUI notification refresh
adds no new worker, charger writes or persistent setting. The original first-test
binary lacked this provider, so its RAM XML tests did not qualify automatic
charging-color updates. The later approved cold-boot candidate includes and
exercises the native provider, as recorded below.
The Advanced list below the buttons is sorted by English display labels while
retaining each item's conditions and action chain.

## Reference-inspired progress and unlock refinements

The local stock-video example was inspected only as a visual reference. No
video, reference frame, watermark or third-party artwork is included in recovery.
Original generated assets use a black pill-shaped track, red outline/glow and
red rounded fill. Patch `0037` adds an opt-in trailing cap to native progress
widgets; bars without the XML flag (including the battery icon) are unchanged.
The percentage above the bar is a validated, floored reading of actual
`ui_progress`, never a timer-based animation. At zero/unknown progress the
twelve-frame red moving segment is used instead of a fabricated percentage.

The PIN keyboard's Enter/check image is also red. Unlock-slider used-fill now
extends under the rounded thumb corner, eliminating the dark gap mid-swipe.
Only the unlock slider opts into centered text and a 56-pixel downward label
offset, constrained to its bounds. Swipe input, activation and action handling
are byte-identical to the pinned native implementation; geometry fixtures cover
empty, tiny, complete, out-of-range and overflow-sized inputs.
The touch harness must perturb raw axes by one unit before each tap: Linux
suppresses unchanged ABS positions across repeated taps, which initially caused
false navigation failures. Quick reboot execution, OTG and actual backup/restore
are not physically qualified by menu tests. RAM-theme Wi-Fi
disconnect/reconnect checks showed a white/green tile and hidden/visible status
icon. The screen timeout remains enabled.

An intermittent missing-text/solid-fill redraw was observed in the existing GPU
path during RAM-theme testing. A software-rendered diagnostic frame was intact.
GPU fault-free rendering alone is therefore not sufficient for release readiness;
this visual discrepancy remains an investigation gate, not a completed fix.

Reports, current image, screenshots and private pretest partition backups live
in `/home/travis/Android/twrp-device-test-20261107.WecOvr/`. Private device logs
and backups are not repository or release assets.

### Approved cold-boot test, latest candidate

`TWRP-infiniti-OxygenOS-modern-progress-20261107.img` was built locally and
flashed only to `recovery_a` under the user's updated test approval. Its SHA-256
is `a928f8f080bef33ed3356921b1fe35f9284716703e7af15b19d3ae05945db36b`;
the physical partition readback matches. Slot A, `recovery_b`, `boot_a` and
`vendor_boot_a` remain unchanged from their pretest values, except for the
explicitly authorized `recovery_a` update. The kernel and both fstabs are unchanged.

The packed image, exact native executable, all assets, Magisk APK and GPU library
pass their image checks. The local build succeeds; all 108 source/host Python
cases, native fixtures and nine installer regular-file tests pass. Clean-source
replay of all 37 recovery patches and external patches is repeat-idempotent.
These checks do not constitute complete hardware or release qualification.

Cold-boot user-0 decryption succeeds with the authorized credential. The brief
ADB disconnect during successful decryption accompanies the USB change to
`mtp,adb`; reconnecting confirms `twrp.user.0.decrypt=1`. Saved Wi-Fi reconnects,
the renderer reports `gles`, and global SELinux remains Enforcing. Charging
indication was checked against the real kernel `Charging` status, not a spoofed
GUI variable. No new charging-mode action was selected by the test harness.

Actual GPU captures show the red PIN check key, red decryption progress bar,
and a continuous mid-swipe red unlock fill. The unlock text is centered and
lowered below the two moving triangles. Evidence: `gui-cold-boot-red-pin-key.png`,
`gui-real-decrypt-red-progress.png`, and `gui-unlock-slider-after.png` in the
private test directory. Swipe activation handling is unchanged.

The experiment is not release-qualified: intermittent GPU text/fill loss and
a RAM-theme-reload/Terminal unresponsive episode still need investigation.
Cold boot recovered the GUI; this does not establish their cause or resolution.
The moving red progress segment also needs a visual boundary-polish pass.
No UI commit, push, workflow build or release was performed.

## Physical testing and rollback gate

Follow-up: the targeted redraw investigation is documented in
[RECOVERY_GPU.md](RECOVERY_GPU.md#font-cache-lifetime-repair-2026-11-07).
Patch `0038` repairs a sanitizer-reproduced native font-cache use-after-free
and path-allocation leak, without disabling GPU rendering. Its font-only image
passed cold-boot decryption, readback and twelve theme-reload comparisons, but
longer WLAN testing reproduced the missing-text symptom. Patch `0039` hardens
GPU vertex ownership and passes the exact-library off-screen fixture, but live
captures still show intermittent loss of fills/status characters. This remains
an investigation gate, not a resolved or release-qualified renderer.

The subsequent native Wi-Fi page is documented in [MODERN_WIFI.md](MODERN_WIFI.md).
Patch `0040` adds optional row selection/password actions, measured signal
columns and synchronized worker/UI updates without an external theme pack.
All 40 recovery patches replay cleanly; the updated host suite contains
119 Python cases plus native/ASan/UBSan fixtures. Installer tests use disposable
regular files, not device partitions. These tests preceded the owner's subsequent
request to commit/push and publish the local preview; no workflow build is needed.
Current artifacts and physical results are in
`/home/travis/Android/twrp-gpu-redraw-20261107.RnPrkS/`.

No phone is flashed or rebooted by these tools. A successful build/static test
does not qualify touch, decryption, display/GPU, USB/OTG or radio on hardware.
The user must confirm the new image's visual appearance and successful decryption
after explicitly approving a physical test.

Keep an exact backup of the currently working installed recovery **before** any
future flash. The earlier exact GPU recovery backup is no longer present in
this restored workspace; do not invent one. A separate published rollback image
is available from the previously validated
[2026-10-25 A/B safety release](https://github.com/travismills82/twrp_device_oplus_infiniti/releases/tag/2026-10-25-c302552):

`401ef2ccba7bcdb4a707ba3ccfb20aca02bb3e3861d9c69ea49f022a2de5985f`.

That release records ColorOS 17.0.0.102 testing; it is not a fresh qualification
against the user's current firmware/kernel. Its hash-verified image is copied
into the local build-artifact directory. A future approved test must first check
product, slot, transport, image compatibility and a working bootloader recovery
path. Preserve `recovery_b`, slot selection and OTA/snapshot state. If rollback
is required, restore only the previously approved `recovery_a` image and verify
its readback; never blindly clone slots or restore modem NV.
