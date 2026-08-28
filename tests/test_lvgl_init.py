# SPDX-License-Identifier: MIT
"""Unit tests for the native lvgl CPython extension."""

import unittest
from pathlib import Path


class LvglInitTests(unittest.TestCase):
    def test_exact_bindings_source_is_recorded(self):
        root = Path(__file__).resolve().parents[1]
        pin = (root / "LVGL_BINDINGS_COMMIT").read_text().strip()
        self.assertEqual(len(pin), 40)
        self.assertTrue(all(character in "0123456789abcdef" for character in pin))

    def test_stub_is_installed_beside_extension(self):
        import lvgl

        extension = Path(lvgl.__file__).resolve()
        self.assertTrue(extension.with_suffix(".pyi").is_file())

    def test_import_and_init_deinit(self):
        import lvgl as lv

        lv.init()
        try:
            self.assertTrue(hasattr(lv, "obj"))
            self.assertTrue(hasattr(lv, "label"))
            self.assertTrue(hasattr(lv, "display_create"))
        finally:
            lv.deinit()

    def test_public_lifecycle_names(self):
        import lvgl as lv

        self.assertTrue(hasattr(lv, "init"))
        self.assertTrue(hasattr(lv, "deinit"))
        self.assertTrue(hasattr(lv, "is_initialized"))
        self.assertFalse(hasattr(lv, "__del__"))

    def test_label_on_active_screen(self):
        import lvgl as lv

        lv.init()
        try:
            disp = lv.display_create(64, 64)
            disp.set_color_format(lv.COLOR_FORMAT.RGB565)
            buf = lv.draw_buf_create(64, 64, lv.COLOR_FORMAT.RGB565, 0)
            disp.set_draw_buffers(buf, None)
            disp.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
            scr = lv.screen_active()
            label = lv.label(scr)
            label.set_text("hi")
            self.assertEqual(label.get_text(), "hi")
        finally:
            lv.deinit()


if __name__ == "__main__":
    unittest.main()
