# SPDX-License-Identifier: MIT
"""Lifetime of Python callbacks set on animations and timers.

A callback set on an lv.anim_t lives while the Python struct or a running
copy of it exists; a timer's callback lives while the timer does. Both are
released on every path LVGL frees them (completion, delete, repeat count,
deinit). The checks run in one subprocess under MALLOC_PERTURB_ so a
use-after-free shows up as a crash rather than luck.
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


class Handler:
    def __init__(self, log=None, tag=None):
        self.log = log
        self.tag = tag
        self.calls = 0

    def __call__(self, *args):
        self.calls += 1
        if self.log is not None:
            self.log.append(self.tag)


def pump(ms):
    for _ in range(ms // 5):
        lv.tick_inc(5)
        lv.timer_handler()


def make_anim(duration, log):
    a = lv.anim_t()
    a.init()
    a.set_var(a)
    a.set_values(0, 10)
    a.set_duration(duration)
    handlers = [Handler(log, "exec"), Handler(log, "completed"), Handler(log, "deleted")]
    a.set_custom_exec_cb(handlers[0])
    a.set_completed_cb(handlers[1])
    a.set_deleted_cb(handlers[2])
    return a, [weakref.ref(h) for h in handlers]


# A. The animation runs to completion; the struct is dropped afterwards.
log = []
a, refs = make_anim(20, log)
a.start()
pump(60)
out["a_fired"] = sorted(set(log))
out["a_alive_with_struct_kept"] = [r() is not None for r in refs]
del a
gc.collect()
out["a_alive_after_struct_dropped"] = [r() is not None for r in refs]

# B. The struct is dropped while the animation is still running.
log = []
a, refs = make_anim(40, log)
a.start()
pump(10)
del a
gc.collect()
out["b_alive_while_running"] = [r() is not None for r in refs]
pump(60)
out["b_fired"] = sorted(set(log))
out["b_running_after"] = lv.anim_count_running()
gc.collect()
out["b_alive_after_completion"] = [r() is not None for r in refs]

# C. The same struct is started again after completing.
log = []
a, refs = make_anim(20, log)
a.start()
pump(60)
a.start()
pump(60)
out["c_completed_calls"] = refs[1]().calls if refs[1]() else None
del a
gc.collect()
out["c_alive_after"] = [r() is not None for r in refs]

# D. A running animation is deleted; deleted_cb runs, then the callbacks go.
log = []
a, refs = make_anim(1000, log)
a.start()
pump(10)
lv.anim_delete_all()
out["d_fired"] = sorted(set(log))
del a
gc.collect()
out["d_alive_after_delete"] = [r() is not None for r in refs]

# E. A timer is created, fires, and is deleted.
log = []
h = Handler(log, "timer")
ref = weakref.ref(h)
t = lv.timer_create(h, 10, None)
del h
pump(30)
out["e_fired"] = len(log) > 0
t.delete()
del t
gc.collect()
out["e_alive_after_delete"] = ref() is not None

# F. A timer whose repeat count runs out is freed by LVGL itself.
h = Handler()
ref = weakref.ref(h)
t = lv.timer_create(h, 10, None)
t.set_repeat_count(1)
del h, t
pump(50)
gc.collect()
out["f_alive_after_repeat_count"] = ref() is not None

# G. A timer deletes itself from its own callback.
class SelfDeleter:
    def __init__(self):
        self.calls = 0

    def __call__(self, timer):
        self.calls += 1
        timer.delete()


h = SelfDeleter()
ref = weakref.ref(h)
lv.timer_create(h, 10, None)
del h
pump(50)
gc.collect()
out["g_calls"] = 1 if ref() is None else ref().calls
out["g_alive_after"] = ref() is not None

# H. set_cb replaces the callback; the timer holds one dict for both.
first, second = Handler(), Handler()
r1, r2 = weakref.ref(first), weakref.ref(second)
t = lv.timer_create(first, 10, None)
t.set_cb(second)
del first, second
pump(30)
out["h_calls"] = [r1().calls if r1() else None, r2().calls if r2() else None]
t.delete()
del t
gc.collect()
out["h_alive_after_delete"] = [r1() is not None, r2() is not None]

# I. Growth over 50 animation and 50 timer cycles, 20 KB per callback.
class Heavy(Handler):
    def __init__(self):
        super().__init__()
        self.buf = bytearray(20 * 1024)


def anim_cycle():
    a = lv.anim_t()
    a.init()
    a.set_var(a)
    a.set_values(0, 10)
    a.set_duration(10)
    a.set_custom_exec_cb(Heavy())
    a.set_completed_cb(Heavy())
    a.start()
    pump(30)


def timer_cycle():
    t = lv.timer_create(Heavy(), 5, None)
    pump(10)
    t.delete()


import tracemalloc
anim_cycle(); timer_cycle(); gc.collect()
tracemalloc.start()
base = tracemalloc.get_traced_memory()[0]
for _ in range(50):
    anim_cycle()
    timer_cycle()
gc.collect()
out["i_growth_bytes"] = tracemalloc.get_traced_memory()[0] - base

lv.deinit()
print(json.dumps(out))
"""


class StructCallbackLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ)
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("MALLOC_PERTURB_", "165")
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, "struct callback lifetime script failed (rc=%r); stdout=%r stderr=%r" % (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        cls.out = json.loads(result.stdout.strip().splitlines()[-1])

    def test_anim_callbacks_released_after_completion_and_struct_dropped(self):
        self.assertEqual(self.out["a_fired"], ["completed", "deleted", "exec"])
        self.assertEqual(self.out["a_alive_with_struct_kept"], [True, True, True])
        self.assertEqual(self.out["a_alive_after_struct_dropped"], [False, False, False])

    def test_anim_outlives_a_dropped_struct_while_running(self):
        self.assertEqual(self.out["b_alive_while_running"], [True, True, True])
        self.assertEqual(self.out["b_fired"], ["completed", "deleted", "exec"])
        self.assertEqual(self.out["b_running_after"], 0)
        self.assertEqual(self.out["b_alive_after_completion"], [False, False, False])

    def test_anim_can_be_restarted_from_the_same_struct(self):
        self.assertEqual(self.out["c_completed_calls"], 2)
        self.assertEqual(self.out["c_alive_after"], [False, False, False])

    def test_anim_deleted_while_running_is_released(self):
        self.assertEqual(self.out["d_fired"], ["deleted", "exec"])
        self.assertEqual(self.out["d_alive_after_delete"], [False, False, False])

    def test_timer_callback_released_on_delete(self):
        self.assertTrue(self.out["e_fired"])
        self.assertFalse(self.out["e_alive_after_delete"])

    def test_timer_callback_released_when_repeat_count_runs_out(self):
        self.assertFalse(self.out["f_alive_after_repeat_count"])

    def test_timer_may_delete_itself_from_its_callback(self):
        self.assertEqual(self.out["g_calls"], 1)
        self.assertFalse(self.out["g_alive_after"])

    def test_timer_set_cb_replaces_and_releases(self):
        self.assertEqual(self.out["h_calls"][0], 0)
        self.assertGreaterEqual(self.out["h_calls"][1], 1)
        self.assertEqual(self.out["h_alive_after_delete"], [False, False])

    def test_cycles_do_not_accumulate(self):
        # 150 callbacks of 20 KB each were registered; the old runtime kept
        # all of them (about 3 MB).
        self.assertLess(self.out["i_growth_bytes"], 64 * 1024)


if __name__ == "__main__":
    unittest.main()
