# SPDX-License-Identifier: MIT
"""Reference counts and buffer exports the runtime hands across to LVGL.

- Reading a callback field back from a struct (``drv.open_cb``) returns a
  new reference to the Python callback; reading it leaves the
  callback's reference count where it was. ``__cast_instance__`` likewise
  returns its struct with a reference of its own, and a struct that owned
  its memory lets go of it rather than freeing it twice.
- A buffer passed where LVGL takes a ``void *`` (``obj.send_event(code,
  buf)``) stays exported until the LVGL call returns, so Python code run
  during the call can't resize it out from under the pointer LVGL holds.
  The export ends when the call returns.

The checks run in one subprocess under MALLOC_PERTURB_ so a use-after-free
shows up as a crash rather than luck.
"""

import json
import os
import subprocess
import sys
import unittest


_SCRIPT = r"""
import json
import sys

import lvgl as lv

lv.init()
disp = lv.display_create(64, 64)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
buf = lv.draw_buf_create(64, 64, lv.COLOR_FORMAT.RGB565, 0)
disp.set_draw_buffers(buf, None)
disp.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
scr = lv.screen_active()
out = {}


# A callback read back from a struct field is a new reference.
def open_cb(drv, path, mode):
    return None

drv = lv.fs_drv_t()
drv.init()
drv.open_cb = open_cb
keep = [open_cb] * 8  # spare references, so a miscount shows as a number, not a crash
before = sys.getrefcount(open_cb)
same = True
for _ in range(4):
    if drv.open_cb is not open_cb:
        same = False
out["funcptr_same_object"] = same
out["funcptr_refcount_delta"] = sys.getrefcount(open_cb) - before


# __cast_instance__ returns the struct with a reference of its own.
area = lv.area_t()
other = lv.area_t()
before = sys.getrefcount(area)
for _ in range(4):
    area.__cast_instance__(other)
out["cast_instance_refcount_delta"] = sys.getrefcount(area) - before


# A buffer handed to LVGL stays exported for the whole call.
data = bytearray(16)
seen = {}

def on_event(e):
    try:
        data.extend(bytes(1 << 16))
        seen["resized"] = True
    except BufferError:
        seen["resized"] = False

code = lv.event_register_id()
btn = lv.button(scr)
btn.add_event_cb(on_event, code, None)
btn.send_event(code, data)
out["resized_during_call"] = seen.get("resized")
try:
    data.extend(b"x")
    out["resizable_after_call"] = True
except BufferError:
    out["resizable_after_call"] = False

btn.delete()
lv.deinit()
print("RESULT " + json.dumps(out))
"""


def _run():
    env = dict(os.environ)
    env["MALLOC_PERTURB_"] = "165"
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return proc, json.loads(line[len("RESULT "):])
    return proc, None


class RuntimeReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc, cls.out = _run()

    def setUp(self):
        if self.out is None:
            self.fail(
                "script did not finish (exit %s)\nstdout:\n%s\nstderr:\n%s"
                % (self.proc.returncode, self.proc.stdout, self.proc.stderr)
            )

    def test_callback_field_read_is_a_new_reference(self):
        self.assertTrue(self.out["funcptr_same_object"])
        self.assertEqual(self.out["funcptr_refcount_delta"], 0)

    def test_cast_instance_returns_a_new_reference(self):
        self.assertEqual(self.out["cast_instance_refcount_delta"], 0)

    def test_buffer_stays_exported_during_the_call(self):
        self.assertIs(self.out["resized_during_call"], False)

    def test_buffer_export_ends_with_the_call(self):
        self.assertIs(self.out["resizable_after_call"], True)


if __name__ == "__main__":
    unittest.main()
