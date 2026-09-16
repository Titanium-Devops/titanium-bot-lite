"""The shipped tree must assume neither POSIX nor a POSIX locale.

0.1.16 could not be imported on Windows for two separate reasons, and a person working
on a Mac could see neither of them:

  * `import fcntl` at the top of two modules, which is a ModuleNotFoundError there;
  * text files read with the platform's default encoding, which is cp1252 on Windows and
    cannot decode the seed files at all.

One line of source each, both fatal before the app ran a line of its own. These checks
read the source rather than the behaviour, so a Mac catches the next one too, without
waiting for a Windows runner or for somebody in the field to hit it.
"""
import ast
import pathlib
import unittest

LITE = pathlib.Path(__file__).resolve().parents[1] / "lite"

# Modules that simply are not there on Windows. Importing one inside a try, or inside a
# function that only runs on POSIX, is fine; this is about the top of a file, where an
# import runs on every platform whether the code below it ever would or not.
POSIX_ONLY = {"fcntl", "termios", "pty", "grp", "pwd", "resource", "posix"}


def _mode_of(call):
    """The string-literal mode a call was given, or None when it named none."""
    for argument in call.args[1:] + [k.value for k in call.keywords if k.arg == "mode"]:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return argument.value
    return None


def _sources():
    for path in sorted(LITE.rglob("*.py")):
        yield path, ast.parse(path.read_bytes(), filename=str(path))


class PortabilityTests(unittest.TestCase):
    def test_every_text_stream_names_its_encoding(self):
        """Default encoding is UTF-8 on this Mac and cp1252 on a tester's Windows."""
        guilty = []
        for path, tree in _sources():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                attribute = isinstance(node.func, ast.Attribute)
                name = node.func.attr if attribute else getattr(node.func, "id", "")
                if name not in ("read_text", "write_text", "open", "fdopen"):
                    continue
                if any(k.arg == "encoding" for k in node.keywords):
                    continue
                if name in ("open", "fdopen"):
                    mode = _mode_of(node)
                    if mode is None and attribute:
                        # An attribute `.open` with no literal mode is something like
                        # urllib's opener, not a file. A bare `open()` still counts.
                        continue
                    if mode is not None and "b" in mode:
                        continue
                    if attribute and getattr(node.func.value, "id", "") == "os":
                        continue                      # os.open returns a descriptor
                guilty.append("%s:%d: %s" % (path.name, node.lineno, name))
        self.assertEqual(guilty, [], "text streams with no encoding=:\n" + "\n".join(guilty))

    def test_no_posix_only_module_is_imported_at_the_top_of_a_file(self):
        guilty = []
        for path, tree in _sources():
            # Only the module body. An import nested in a try or a function is guarded
            # by construction, which is exactly how filelock.py reaches fcntl.
            for node in tree.body:
                if not isinstance(node, ast.Import):
                    continue
                for item in node.names:
                    if item.name.split(".")[0] in POSIX_ONLY:
                        guilty.append("%s:%d: import %s" % (path.name, node.lineno, item.name))
        self.assertEqual(guilty, [], "unguarded POSIX-only imports:\n" + "\n".join(guilty))

    def test_the_seed_files_are_not_decodable_by_accident(self):
        """The check above only matters because these files really are not ASCII.

        If the seeds ever became plain ASCII the encoding test would keep passing while
        proving nothing, so pin the thing that made cp1252 fail in the first place.
        """
        seeds = [p for p in (LITE / "seeds").rglob("*") if p.is_file()]
        self.assertTrue(seeds, "no seed files found")
        self.assertTrue(any(any(byte > 0x7F for byte in p.read_bytes()) for p in seeds),
                        "no seed file has a byte outside ASCII any more")


if __name__ == "__main__":
    unittest.main()
