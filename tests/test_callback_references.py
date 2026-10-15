# SPDX-License-Identifier: MIT
"""References a callback trampoline holds while LVGL calls into Python.

- A callback that replaces its own registration while it runs
  (``timer.set_cb(other)`` from inside the timer callback) stays alive until
  it returns. Before, the only reference was the callback dict's, so the
  replacement freed the callback mid-call.
- Arguments passed to a callback are released after the call. Before, every
  call leaked one reference to each argument, so a widget handed to a
  ``tree_walk`` callback was never freed.

The checks run in one subprocess under MALLOC_PERTURB_ so a use-after-free
shows up as a crash rather than luck.
"""

import json
import os
import subprocess
import sys
import unittest


_SCRIPT = r"""
import gc
import json
import sys
import weakref

import lvgl as lv

lv.init()
disp = lv.display_create(64, 64)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
buf = lv.draw_buf_create(64, 64, lv.COLOR_FORMAT.RGB565, 0)
disp.set_draw_buffers(buf, None)
disp.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
scr = lv.screen_active()
out = {}


def pump(ms):
    for _ in range(ms // 5):
        lv.tick_inc(5)
        lv.timer_handler()


# A callback that replaces itself stays alive until it returns.
timer = lv.timer_create_basic()
timer.set_period(10)


class Replaces:
    def __call__(self, t):
        ref = weakref.ref(self)
        del self
        timer.set_cb(lambda t: None)
        gc.collect()
        out["alive_after_replacing_itself"] = ref() is not None


timer.set_cb(Replaces())
pump(50)
timer.delete()


# Callback arguments are released after the call.
child = lv.button(scr)

def walk(obj, user_data):
    return lv.obj.TREE_WALK.NEXT

before = sys.getrefcount(child)
for _ in range(10):
    scr.tree_walk(walk, None)
out["tree_walk_arg_refcount_delta"] = sys.getrefcount(child) - before

child.delete()
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


class CallbackReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc, cls.out = _run()

    def setUp(self):
        if self.out is None:
            self.fail(
                "script did not finish (exit %s)\nstdout:\n%s\nstderr:\n%s"
                % (self.proc.returncode, self.proc.stdout, self.proc.stderr)
            )

    def test_callback_outlives_replacing_itself(self):
        self.assertIs(self.out.get("alive_after_replacing_itself"), True)

    def test_callback_arguments_are_released(self):
        self.assertEqual(self.out["tree_walk_arg_refcount_delta"], 0)


if __name__ == "__main__":
    unittest.main()
