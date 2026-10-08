# SPDX-License-Identifier: MIT
"""JPEG images draw scaled and contained, as they do on MicroPython.

The JPEG decoder is jpegio's (src/jpegio/, JPEGIO_COMMIT), which decodes the
whole image when it opens. LVGL's own TJPGD decoded tiles, which LVGL can't
transform: a scaled or contained JPEG drew a garbled crop, or nothing.
"""

import ast
import subprocess
import sys
import unittest

# 64 x 64, four quadrants: red, green / blue, white. Baseline 4:2:0, JFIF.
_QUADS_JPEG = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsK"
    "CwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQU"
    "FBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCABAAEADASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD50ooo"
    "r8MP9UwooooA+xqKKK/Ej/mPCiiigD45ooor9tP+nAKKKKAPsaiiivxI/wCY8KKKKAPy8ooor/oz"
    "P7lCiiigD+luiiiv8rD7gKKKKAP5pKKKK/1TPhwooooA/pbooor/ACsPuAooooA//9k="
)

_SCRIPT = """
import base64
import lvgl as lv

data = base64.b64decode(%r)
lv.init()
disp = lv.display_create(80, 80)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
buf = lv.draw_buf_create(80, 80, lv.COLOR_FORMAT.RGB565, 0)
disp.set_draw_buffers(buf, None)
disp.set_render_mode(lv.DISPLAY_RENDER_MODE.FULL)
disp.set_flush_cb(lambda d, a, p: d.flush_ready())
scr = lv.screen_active()
scr.set_style_bg_color(lv.color_black(), 0)

dsc = lv.image_dsc_t()
dsc.header.magic = lv.IMAGE_HEADER_MAGIC
dsc.header.cf = lv.COLOR_FORMAT.RAW
dsc.data = data
dsc.data_size = len(data)


def pixel(snap, x, y):
    stride = snap.header.stride
    raw = bytes(snap.data.__dereference__(stride * snap.header.h))
    v = raw[y * stride + 2 * x] | raw[y * stride + 2 * x + 1] << 8
    return (v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3


for mode in ("native", "contain", "scale"):
    img = lv.image(scr)
    img.set_src(dsc)
    if mode == "contain":
        img.set_size(40, 40)
        img.set_inner_align(lv.image.ALIGN.CONTAIN)
    elif mode == "scale":
        img.set_scale(160)  # 160/256 of 64 px: 40 px
    img.center()
    lv.refr_now(disp)
    snap = lv.snapshot_take(scr, lv.COLOR_FORMAT.RGB565)
    size = 64 if mode == "native" else 40
    x0 = (80 - size) // 2
    a, b = x0 + size // 4, x0 + 3 * size // 4
    print(mode, [pixel(snap, x, y) for x, y in ((a, a), (b, a), (a, b), (b, b))])
    img.delete()
"""


def _close(got, want):
    return all(abs(g - w) <= 24 for g, w in zip(got, want))


class JpegDecoderTest(unittest.TestCase):
    def test_jpeg_draws_native_contained_and_scaled(self):
        out = subprocess.run(
            [sys.executable, "-c", _SCRIPT % "".join(_QUADS_JPEG)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        want = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
        rows = [line for line in out.stdout.splitlines() if line.split(" ")[0] in ("native", "contain", "scale")]
        self.assertEqual(len(rows), 3, out.stdout)
        for row in rows:
            mode, rest = row.split(" ", 1)
            got = ast.literal_eval(rest)
            for g, w in zip(got, want):
                self.assertTrue(_close(g, w), "%s: quadrants %r, want %r" % (mode, got, want))

    def test_lvgl_tjpgd_is_not_exposed(self):
        import lvgl as lv

        self.assertFalse(hasattr(lv, "tjpgd_init"))
        self.assertFalse(hasattr(lv, "tjpgd_deinit"))


if __name__ == "__main__":
    unittest.main()
