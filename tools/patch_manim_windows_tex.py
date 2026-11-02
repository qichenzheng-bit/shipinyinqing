"""Fix Manim Community 0.22.1's Windows MiKTeX absolute TeX input path.

TeX parses an unquoted absolute file argument as TeX input tokens. Windows
8.3 aliases (RUNNER~1), spaces and localized profile paths can therefore
cause an invalid input file, even though the PDF/TeX installation works.

Compile from the existing TeX folder with a filename only, using '.' as the
output directory. The DVI/SVG artifact paths used by Manim are unchanged.
Applied ONLY to the bundled, pinned runtime during CI staging.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from importlib.metadata import version
from pathlib import Path

PINNED_MANIM = "0.22.1"
MARKER = "WEIGUANG_WINDOWS_MIKTEX_RELATIVE_INPUT"
ORIGINAL = (
    "                command = make_tex_compilation_command(\n"
    "                    compiler,\n"
    "                    output_format,\n"
    "                    tex_file,\n"
    "                    tex_dir,\n"
    "                )\n"
    "                cp = subprocess.run(command, stdout=subprocess.DEVNULL)\n"
)
REPLACEMENT = (
    f"                # {MARKER}: avoid absolute TeX input paths on Windows.\n"
    "                # Compile inside the output folder, using a plain basename.\n"
    "                command = make_tex_compilation_command(\n"
    "                    compiler,\n"
    "                    output_format,\n"
    "                    Path(tex_file.name),\n"
    '                    Path("."),\n'
    "                )\n"
    "                cp = subprocess.run(\n"
    "                    command, stdout=subprocess.DEVNULL, cwd=tex_dir\n"
    "                )\n"
)


def patch_source(source: str) -> str:
    if MARKER in source:
        if source.count(MARKER) != 1 or REPLACEMENT not in source:
            raise RuntimeError("MANIM_TEX_PATCH_MARKER_INCONSISTENT")
        return source
    if source.count(ORIGINAL) != 1:
        raise RuntimeError("MANIM_TEX_UPSTREAM_LAYOUT_CHANGED; refuse unsafe patch")
    patched = source.replace(ORIGINAL, REPLACEMENT)
    ast.parse(patched)
    return patched


def self_test() -> None:
    source = "from pathlib import Path\ndef compile_tex():\n" + ORIGINAL
    patched = patch_source(source)
    assert patch_source(patched) == patched
    assert MARKER in patched
    assert "Path(tex_file.name)" in patched
    assert "cwd=tex_dir" in patched
    try:
        patch_source(source.replace(ORIGINAL, "    pass\n"))
    except RuntimeError as exc:
        assert "UPSTREAM_LAYOUT_CHANGED" in str(exc)
    else:
        raise AssertionError("MISSING_FAIL_CLOSED_GUARD")
    print("WINDOWS_MANIM_TEX_PATCH_SELF_TEST_PASSED")


def main() -> None:
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    if sys.argv[1:]:
        raise SystemExit("usage: patch_manim_windows_tex.py [--self-test]")
    detected = version("manim")
    if detected != PINNED_MANIM:
        raise RuntimeError(
            f"EXPECTED_MANIM_{PINNED_MANIM}_GOT_{detected}; update the patch first"
        )
    manim_spec = importlib.util.find_spec("manim")
    if manim_spec is None or manim_spec.origin is None:
        raise RuntimeError("MANIM_MODULE_NOT_FOUND")
    file = Path(manim_spec.origin).parent / "utils" / "tex_file_writing.py"
    if not file.is_file():
        raise RuntimeError(f"MANIM_TEX_MODULE_NOT_FOUND: {file}")
    before = file.read_text(encoding="utf-8")
    after = patch_source(before)
    if after != before:
        file.write_text(after, encoding="utf-8")
    assert MARKER in file.read_text(encoding="utf-8")
    print("WINDOWS_MANIM_TEX_RELATIVE_INPUT_PATCH_PASSED")


if __name__ == "__main__":
    main()
