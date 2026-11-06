# Adreno GLES GUI compositor (experimental)

Patch `0029-gui-adreno-gles-compositor.patch` adds real GPU composition to
minuitwrp. Solid fills, PNG/circle textures and FreeType's A8 text masks are
drawn by GLES on Adreno. DRM/fbdev scanout is unchanged. This is not SurfaceFlinger,
Vulkan, or zero-copy scanout: completed pixels are read back to the existing
framebuffer, using only the clipped damage bounding box for partial updates.
Patch `0030` adds the incremental relink dependency on the actual minuitwrp DSO,
not just its exported-symbol table. `scripts/verify-gpu-image.py` unpacks the final
image and requires its GUI library to be byte-identical to the newly built library;
it also checks startup files, dependencies and exclusion of developer/UFS tools.

## Startup and fallback

`twrp-gpu-start` runs after fstab preparation. It verifies slot `_a`/`_b`, mounts
that slot's vendor/system/vendor_dlkm read-only (ext4 uses `noload`), rejects
wrong-slot or writable views, and uses the installed firmware's module dependency
graph and blocklist. It does not force-load modules, change GPU clocks, write
partitions, change either fstab, or change SELinux enforcement.

Only gen8 GPU firmware is copied into RAM, with `vendor_file` labels readable
by the existing ueventd policy; no large GPU blob payload is bundled. A total
8 MiB limit applies (the qualified firmware supplies 791,806 bytes). A separate
20-second-bounded shader/readback probe must pass before `twrp.gpu.ready=1`.
Its library environment applies only to that diagnostic subprocess.

The GUI opens vendor EGL/GLES in a dedicated linker namespace. Only bionic and
the real Android linker interfaces are shared with recovery; vendor/framework
C++ libraries do not replace the GUI's process-wide libraries. Sharing
`libdl_android.so` and `ld-android.so` is essential: loading the on-disk linker
placeholder in the new namespace caused a diagnostic SIGTRAP during development,
which the off-screen fixture caught before GUI deployment. No CFI checks were
disabled to fix it.

Before dependencies are ready, or if EGL/config/shader setup fails, the normal
CPU renderer remains available. A bounded 32 MiB / 8192-command journal retains
pending primitives and texture bytes. A GLES error/context loss detected during
drawing/readback replays that pending frame with Pixelflinger before disabling
the GPU. This is error fallback, not protection against an arbitrary hung/crashed
vendor driver or kernel. No in-process driver call is claimed to be uncrashable.

Pattern-lock lines retain their original CPU rasterization; the framebuffer is
synchronized before CPU writes and re-uploaded before further GPU composition.
Screenshots synchronize pending GPU drawing. Unsupported formats and rotated
framebuffers retain the software path. Supported GPU targets are RGBA/RGBX
32-bit, portrait/unrotated, up to 4096 pixels per dimension.

## Diagnostics

From a root recovery shell:

```sh
getprop twrp.gpu.status       # preparing / ready / failure reason
getprop twrp.gpu.renderer     # cpu / gles-pending / gles / cpu-disabled / cpu-fallback
getprop twrp.gpu.frames       # completed GPU-composited frames
setprop twrp.gpu.enable 0     # software mode at the next rendered frame
setprop twrp.gpu.enable 1     # re-enable after an explicit software-mode transition
```

A failure after an attempted initialization is not retried continuously. CPU
fallback is always available when dependencies cannot be qualified. For a CPU-only
boot test, set `twrp.gpu.enable=0` before running the helper/GUI in the test ramdisk.
This is a per-boot diagnostic property, not a persistent user preference.

`setprop twrp.gpu.capture 1` requests a screenshot at the next GUI flip, saved
only to `/tmp/twrp-gpu-ui.png`. Wait for the property to return to `0` before
pulling the complete PNG. Screen timeout remains enabled: wake/unlock the display
if rendering has stopped. The capture facility works in software mode as well.

The developer-only `twrp-gpu-render-test` is built with the Android toolchain,
is marked `installable: false`, and is not a normal recovery payload. It compares
off-screen GLES against the same Pixelflinger implementation for opaque and
transparent fills, clipping, RGBA/RGBX images, cropped A8 masks, padded strides,
partial frame preservation, CPU-write synchronization and pending-frame fallback.
Run it from RAM against the matching libminuitwrp; `--benchmark` adds a native
1272x2772 full-fill workload. It never opens a block device or DRM scanout.

## Qualification boundary

The connected COS17 phone passed actual Adreno 840 shader/readback testing in
recovery, not only Android. The normal-toolchain 64x64 compositor fixture passed
with maximum RGB difference 1 against software. A full-resolution diagnostic run
passed the same cases. Live GUI testing used a temporary RAM library bind in the
already-installed recovery: main/Advanced rendering, touch navigation, software
mode, re-enabling GLES, and screen timeout/wake were exercised. A matched main-page
CPU/GLES screenshot comparison, excluding the changing status bar, had maximum
RGB difference 3/255 (only three pixels exceeded difference 2).

After 54 live GPU-composited frames, all eight KGSL GPU fault counters and all
seven IOMMU page-fault columns were zero. Global SELinux remained Enforcing. This
does not qualify every firmware/kernel combination, all touch patterns, new
backup/restore targets, or decryption stability. A second, fresh recovery boot
started with no KGSL node: the unmodified startup helper loaded KGSL normally,
passed its separate shader probe, then passed the compositor fixture again.
The exact final built GUI library was also tested by a RAM bind after that cold
start, with working GLES GUI captures and zero GPU/IOMMU fault counters. Final
packed-image results are recorded with the build artifacts.

Performance must not be overstated: an early full-screen opaque fill +100-rectangle
benchmark measured 6.20 ms/frame CPU versus 7.17 ms/frame GLES including readback.
Actual workload and damage size matter. GPU composition is available, but a
blanket speed/battery improvement is not claimed. Zero-copy GPU-to-DRM buffers
and bounded texture caching are possible future optimizations, not enabled here.

The GPU views keep active vendor/system/vendor_dlkm in use. Do not force-unmount
them to restore those partitions while code/firmware is live. Native restore
guards must reject mounted/in-use targets; deliberate CPU-only recovery preparation
and quiescence of the other active HALs are needed for such restoration. Stopping
GPU drawing alone does not make mapped vendor code safe to overwrite.

Architecture references: [Android linker namespaces](https://source.android.com/docs/core/architecture/vndk/linker-namespace)
and [Khronos EGL](https://registry.khronos.org/EGL/).
