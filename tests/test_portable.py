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

ROOT = pathlib.Path(__file__).resolve().parents[1]
LITE = ROOT / "lite"
TESTS = ROOT / "tests"

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


def _sources(*folders):
    for folder in folders or (LITE,):
        for path in sorted(folder.rglob("*.py")):
            yield path, ast.parse(path.read_bytes(), filename=str(path))


class PortabilityTests(unittest.TestCase):
    def test_every_text_stream_names_its_encoding(self):
        """Default encoding is UTF-8 on this Mac and cp1252 on a tester's Windows."""
        guilty = []
        for path, tree in _sources(LITE, TESTS):
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


class PathShapeTests(unittest.TestCase):
    """A path the model is shown, or that the code matches on, is spelled with slashes.

    str(Path) uses the OS separator, so on Windows the skills catalog read
    `skills\\greeting\\SKILL.md` in the prompt, and worse, select_memories filters facts
    on a "memory/log/" prefix that a backslash path can never match. Memory recall
    simply returned nothing there, with no error to say so.
    """

    def setUp(self):
        import tempfile
        from lite import server
        folder = tempfile.TemporaryDirectory(prefix="lite-paths-")
        self.addCleanup(folder.cleanup)
        self.root = pathlib.Path(folder.name)
        self.server = server
        (self.root / "memory/log").mkdir(parents=True)
        (self.root / "memory/log/2026-09-16.md").write_text(
            "- (2026-09-16) The owner keeps bees.\n", encoding="utf-8")
        (self.root / "skills/greeting").mkdir(parents=True)
        (self.root / "skills/greeting/SKILL.md").write_text(
            "---\nname: Greeting\ndescription: Say hello\n---\nSay hello.\n", encoding="utf-8")

    def test_memory_and_skill_paths_use_forward_slashes(self):
        for row in self.server.read_memories(self.root) + self.server.read_skills(self.root):
            self.assertNotIn("\\", row["path"], row)
        self.assertEqual([m["path"] for m in self.server.read_memories(self.root)],
                         ["memory/log/2026-09-16.md"])
        self.assertEqual([s["path"] for s in self.server.read_skills(self.root)],
                         ["skills/greeting/SKILL.md"])

    def test_a_saved_fact_still_reaches_the_prompt(self):
        """The prefix match select_memories does is the thing backslashes broke."""
        memories, profile, recent, surfaced = self.server.select_memories(self.root, "bees", None)
        self.assertEqual([m["name"] for m in recent], ["The owner keeps bees."])


if __name__ == "__main__":
    unittest.main()
