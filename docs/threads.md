# Threads

Drive LVGL from one thread. Every `lvgl` call happens on that thread:
creating widgets, setting their properties, `lv.timer_handler()`,
`lv.refr_now()`. Your callbacks run there too, because LVGL calls them from
inside those calls.

Every `lvgl` object is also let go of on that thread: a widget, a struct
such as an `lv.anim_t`, a callback you handed to LVGL. In practice that
means keeping them in variables the LVGL thread owns, and never passing
them to another thread to drop.

Other threads can run any Python that doesn't touch `lvgl`: audio,
networking, file I/O, number crunching. Send their results to the LVGL
thread through a `queue.Queue` and apply them there.

## On a free-threaded Python

On a free-threaded build (3.15t wheels are published), `lvgl` declares that
it doesn't need the GIL, so importing it leaves the GIL off and your other
threads run in parallel with drawing.

The one-thread rule is what makes that safe. LVGL isn't thread-safe, and the
binding keeps shared state of its own with no lock around it: scratch
buffers for converting structs, the table of callbacks it holds for you, and
the references it lets go of once a call returns. Two threads calling
`lvgl` at once can corrupt that state on any build; without the GIL it
happens sooner.

One thing to watch: if `lvgl` objects sit in a reference cycle, the cycle
collector frees them on whichever thread it happens to run. In a threaded
program, delete widgets yourself on the LVGL thread (`widget.delete()`)
rather than leaving them to the collector.

## Checking it

`tests/test_free_threading.py` runs on free-threaded builds. It checks that
importing `lvgl` leaves the GIL off, and that frames drawn on one thread
while other threads run Python are byte for byte the frames drawn alone.
