# SPDX-License-Identifier: MIT
"""Unit tests for the native lvgl CPython extension."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


_ATEXIT_DEINIT_SCRIPT = """
import atexit

import lvgl as lv

lv.init()
disp = lv.display_create(64, 64)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
buf = lv.draw_buf_create(64, 64, lv.COLOR_FORMAT.RGB565, 0)
disp.set_draw_buffers(buf, None)
disp.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
scr = lv.screen_active()

widgets = []


class Row:
    def __init__(self, parent, i):
        self.btn = lv.button(parent)
        self.label = lv.label(self.btn)
        self.label.set_text("r%d" % i)
        # Bound-method callbacks registered for several event types so the
        # per-object event dsc list has several per-registration callback
        # dicts by the time lv_deinit() walks it.
        self.btn.add_event_cb(self.on_click, lv.EVENT.CLICKED, None)
        self.btn.add_event_cb(self.on_value_changed, lv.EVENT.VALUE_CHANGED, None)
        self.btn.add_event_cb(self.on_delete, lv.EVENT.DELETE, None)

    def on_click(self, event):
        self.label.set_text("clicked")

    def on_value_changed(self, event):
        pass

    def on_delete(self, event):
        pass


for i in range(40):
    widgets.append(Row(scr, i))
kept = widgets


def _deinit_at_exit():
    lv.deinit()


# pydevices' display_driver registers its LVGL teardown the same way: an
# atexit hook that calls lv.deinit() during interpreter shutdown. lv_deinit()
# fires LV_EVENT_DELETE per object, which used to crash inside
# lvpy_release_callback_user_data (PyDict_Check / PyObject_TypeCheck on a
# stored callback user_data pointer) once Python began tearing itself down.
atexit.register(_deinit_at_exit)
"""


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

    def test_atexit_deinit_does_not_crash(self):
        # Regression test for the use-after-free in
        # lvpy_release_callback_user_data() during interpreter finalization
        # (fixed by guarding the release path with Py_IsFinalizing() /
        # _Py_IsFinalizing()). Runs in a subprocess because the crash only
        # reproduces on real interpreter shutdown, not inside a running test.
        env = dict(os.environ)
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        result = subprocess.run(
            [sys.executable, "-c", _ATEXIT_DEINIT_SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            "atexit-triggered lv.deinit() crashed (rc=%r); stdout=%r stderr=%r"
            % (result.returncode, result.stdout, result.stderr),
        )


if __name__ == "__main__":
    unittest.main()
