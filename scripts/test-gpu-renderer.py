#!/usr/bin/env python3
"""Recovery GPU source/build safety contracts. No ADB or block writes."""
from pathlib import Path
import subprocess
import sys
import unittest

DEVICE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else DEVICE.parents[2]
MINUI = ROOT / "bootable/recovery/minuitwrp"

class GpuTests(unittest.TestCase):
    def test_optin_and_cpu_format_fallback(self):
        source=(MINUI / "graphics_gles.cpp").read_text()
        self.assertIn('property_get_bool("twrp.gpu.ready", false)',source)
        self.assertIn('property_get_bool("twrp.gpu.enable", true)',source)
        self.assertIn('GGL_PIXEL_FORMAT_RGBX_8888',source)
        self.assertIn('"not a hardware Adreno renderer"',source)
        graphics=(MINUI / "graphics.cpp").read_text()
        self.assertIn('if (gr_rotation == 0) gr_gpu_init',graphics)

    def test_loader_is_isolated_not_global(self):
        source=(MINUI / "graphics_gles.cpp").read_text()
        self.assertIn('android_create_namespace("twrp_gles"',source)
        self.assertIn('ANDROID_DLEXT_USE_NAMESPACE',source)
        self.assertIn('"libc.so:libm.so:libdl.so:libdl_android.so:ld-android.so"',source)
        self.assertNotIn('setenv(',source)
        self.assertNotIn('system(',source)

    def test_bounded_replay_and_readback_commit(self):
        source=(MINUI / "graphics_gles.cpp").read_text()
        self.assertIn('kLimit = 32 * 1024 * 1024',source)
        self.assertIn('journal.size() >= 8192',source)
        self.assertIn('if (cpu && !journal.empty()) Replay();',source)
        flush=source[source.index('    void Flush()'):source.index('    bool Draw(')]
        self.assertLess(flush.index('glReadPixelsFn('),flush.index('Check(glGetErrorFn()'))
        self.assertLess(flush.index('Check(glGetErrorFn()'),flush.index('memcpy(target->data'))
        self.assertIn('height-1-y',flush)
        self.assertIn('target->height-bottom',flush)
        self.assertIn('target->row_bytes',flush)

    def test_text_and_screenshots_are_synchronized(self):
        self.assertIn('gr_gpu_blit(&e->surface', (MINUI / "truetype.cpp").read_text())
        self.assertIn('gr_gpu_flush();', (MINUI / "graphics_utils.cpp").read_text())
        source=(MINUI / "graphics.cpp").read_text()
        line=source[source.index('void gr_line('):source.index('gr_surface gr_render_circle(')]
        self.assertIn('gr_gpu_cpu_write();',line)
        self.assertIn('gl->linex(',line)

    def test_active_readonly_driver_sources(self):
        helper=(DEVICE / 'recovery/root/system/bin/twrp-gpu-start').read_text()
        self.assertIn('/dev/block/mapper/${name}${slot}',helper)
        self.assertIn('case "$slot" in _a|_b)',helper)
        self.assertIn('mount -t ext4 -o ro,noload',helper)
        self.assertIn('mount -t erofs -o ro',helper)
        self.assertIn('timeout 20 modprobe -b',helper)
        self.assertIn('timeout 20 env LD_LIBRARY_PATH=',helper)
        self.assertIn('shader-probe-unverified',helper)
        self.assertIn('wrong-slot-view',helper)
        self.assertIn('8388608',helper)
        for forbidden in ('setenforce','rmmod','insmod -f','dd if=','fastboot ','export LD_LIBRARY_PATH','force_clk_on'):
            self.assertNotIn(forbidden,helper)
        init=(DEVICE / 'recovery/root/init.recovery.qcom.rc').read_text()
        self.assertIn('service twrp-gpu-start /system/bin/twrp-gpu-start',init)

    def test_firmware_selection(self):
        pattern='gen8[0-9][0-9][0-9][0-9]_aqe.fw|gen8[0-9][0-9][0-9][0-9]_sqe.fw|gen8[0-9][0-9][0-9][0-9]_gmu.bin|gen8[0-9][0-9][0-9][0-9]_zap.mbn'
        helper=(DEVICE / 'recovery/root/system/bin/twrp-gpu-start').read_text()
        self.assertIn(pattern,helper)
        for name,accepted in [('gen80200_sqe.fw',True),('gen80000_gmu.bin',True),('gen80900_zap.mbn',True),
                              ('gen80200_aqe.fw',True),('gen80200.ko',False),('wlan.mbn',False),('../gen80200_zap.mbn',False)]:
            result=subprocess.run(['sh','-c',f'case "$1" in {pattern}) exit 0;; *) exit 1;; esac','test',name])
            self.assertEqual(result.returncode==0,accepted,name)

    def test_real_gpu_fixture_is_not_bundled(self):
        source=(DEVICE / 'tools/gpu_render_test.cpp').read_text()
        for label in ('pending-frame CPU fallback replay','persistent partial frame','cropped A8 text','CPU line/snapshot synchronization'):
            self.assertIn(label,source)
        product=(DEVICE / 'device.mk').read_text()
        self.assertNotIn('twrp-gpu-render-test',product)
        self.assertIn('twrp-gpu-start',product)
        self.assertIn('installable: false', (DEVICE / 'Android.bp').read_text())

    def test_incremental_library_staging_depends_on_renderer(self):
        source=(ROOT / 'bootable/recovery/prebuilt/Android.mk').read_text()
        relink=source[source.index('LOCAL_MODULE := relink_libraries'):source.index('LOCAL_MODULE := relink_binaries')]
        self.assertIn('LOCAL_ADDITIONAL_DEPENDENCIES += $(TARGET_OUT_SHARED_LIBRARIES)/libminuitwrp.so',relink)
        self.assertIn('$(TARGET_OUT_SHARED_LIBRARIES)/bootstrap/libdl_android.so',relink)

if __name__=='__main__': unittest.main(argv=[sys.argv[0]],verbosity=2)
