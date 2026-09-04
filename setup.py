"""Build the lvgl CPython extension (generated/lvgl_python.c + LVGL sources)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

ROOT = Path(__file__).resolve().parent
LVGL_DIR = ROOT / "lvgl"
GENERATED = ROOT / "generated" / "lvgl_python.c"
GENERATED_PYI = ROOT / "generated" / "lvgl.pyi"
BINDINGS_PIN = ROOT / "LVGL_BINDINGS_COMMIT"

if not GENERATED.is_file():
    raise SystemExit(
        f"{GENERATED} not found. Run: {ROOT / 'scripts/sync_from_lvgl_bindings.sh'}"
    )

if not BINDINGS_PIN.is_file() or len(BINDINGS_PIN.read_text().strip()) != 40:
    raise SystemExit("LVGL_BINDINGS_COMMIT must contain the exact source commit")

if not (LVGL_DIR / "lvgl.h").is_file():
    raise SystemExit(
        "lvgl submodule missing. Run: git submodule update --init lvgl"
    )

# LVGL's built-in TJPGD stays on for CPython (lv_conf.h: LV_USE_TJPGD 1 under
# LV_CPYTHON_BUILD) -- CPython has no jpegio, so tjpgd.c compiles like the rest.
lvgl_sources = [
    os.path.relpath(p, ROOT)
    for p in (LVGL_DIR / "src").rglob("*.c")
]

runtime_sources = [
    "src/lvpy_runtime.c",
    "generated/lvgl_python.c",
]

include_dirs = [
    str(ROOT),
    str(ROOT / "src"),
    str(LVGL_DIR),
]

define_macros = [("LV_CPYTHON_BUILD", "1")]

if sys.platform == "win32":
    extra_compile_args = ["/wd4101", "/wd4244", "/wd4267", "/wd4996"]
else:
    extra_compile_args = [
        "-Wno-unused-function",
        "-Wno-sign-compare",
        "-Wno-incompatible-pointer-types",
        "-Wno-unused-variable",
        "-Wno-deprecated-declarations",
    ]

ext = Extension(
    "lvgl",
    sources=runtime_sources + lvgl_sources,
    include_dirs=include_dirs,
    define_macros=define_macros,
    extra_compile_args=extra_compile_args,
)


class Win32LinkRspBuildExt(build_ext):
    """MSVC link.exe has an ~8k command-line limit; LVGL needs a response file."""

    def run(self):
        super().run()
        self._install_pyi_stubs()

    def _install_pyi_stubs(self) -> None:
        pyi_src = GENERATED_PYI
        if not pyi_src.is_file():
            return
        for ext in self.extensions:
            if ext.name != "lvgl":
                continue
            ext_path = Path(self.get_ext_fullpath(self.get_ext_fullname(ext.name)))
            dest = ext_path.with_suffix(".pyi")
            dest.write_bytes(pyi_src.read_bytes())

    def build_extensions(self):
        if sys.platform == "win32":
            self._patch_msvc_link()
        super().build_extensions()

    def _patch_msvc_link(self) -> None:
        try:
            from setuptools._distutils import _msvccompiler as msvc
        except ImportError:
            return
        compiler_cls = getattr(msvc, "MSVCCompiler", None)
        if compiler_cls is None or getattr(compiler_cls.link, "_lvcp_rsp", False):
            return

        orig_link = compiler_cls.link

        def link_with_rsp(
            compiler,
            target_desc,
            objects,
            output_filename,
            output_dir,
            libraries,
            library_dirs,
            runtime_library_dirs,
            export_symbols,
            debug,
            extra_preargs,
            extra_postargs,
            build_temp,
            target_lang,
        ):
            obj_count = len(objects)
            real_build_temp = build_temp
            if not real_build_temp and objects and not str(objects[0]).startswith("@"):
                real_build_temp = os.path.dirname(objects[0])
            if obj_count > 50:
                if not real_build_temp:
                    real_build_temp = str(ROOT / "build" / "msvc")
                os.makedirs(real_build_temp, exist_ok=True)
                rsp_path = os.path.join(real_build_temp, "lvgl_link_objects.rsp")
                with open(rsp_path, "w", encoding="utf-8") as rsp:
                    for obj in objects:
                        rsp.write(f'"{obj}"\n')
                objects = [f"@{rsp_path}"]

            orig_dirname = os.path.dirname

            def dirname_fixup(path: str) -> str:
                if isinstance(path, str) and path.startswith("@"):
                    return real_build_temp or orig_dirname(path[1:])
                return orig_dirname(path)

            os.path.dirname = dirname_fixup
            try:
                return orig_link(
                    compiler,
                    target_desc,
                    objects,
                    output_filename,
                    output_dir,
                    libraries,
                    library_dirs,
                    runtime_library_dirs,
                    export_symbols,
                    debug,
                    extra_preargs,
                    extra_postargs,
                    real_build_temp,
                    target_lang,
                )
            finally:
                os.path.dirname = orig_dirname

        link_with_rsp._lvcp_rsp = True
        compiler_cls.link = link_with_rsp


setup(
    name="pydevices-lvgl",
    description="LVGL bindings for CPython (generated)",
    ext_modules=[ext],
    py_modules=["display_driver", "fs_driver"],
    python_requires=">=3.9",
    cmdclass={"build_ext": Win32LinkRspBuildExt},
)
