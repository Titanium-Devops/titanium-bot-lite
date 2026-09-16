"""The single-owner lock has to refuse a second process on whatever OS this is.

Titanium Tiiny Bot 0.1.16 could not even be imported on Windows, so the lock behind
`one owner per data directory` and `one caller per Tiiny` had never run there at all.
These tests take the lock for real and make a genuinely separate process try for it.
"""
import multiprocessing
import os
import tempfile
import unittest

from lite import filelock


def _take_the_lock(path, answer):
    """Run in a spawned child: open the file ourselves and say what the lock did."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            filelock.lock_nb(fd)
        except BlockingIOError:
            answer.put("refused")
        else:
            answer.put("taken")
            filelock.unlock(fd)
    finally:
        os.close(fd)


class FileLockTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="lite-filelock-")
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "one.lock")
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(self._close)

    def _close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def _second_process(self):
        """What a separate process makes of the lock: "taken" or "refused".

        Spawn, not fork, and not for tidiness. A forked child inherits this descriptor,
        and a POSIX lock lives on the open file description the two copies then share,
        so the child would be handed the very lock it is meant to be refused and the
        test would pass while proving nothing. A spawned child opens the file itself,
        which is what a second Tiiny app on the machine actually does. subprocess would
        do as well and is not available: the farm's archive scanner forbids it outright.
        """
        context = multiprocessing.get_context("spawn")
        answer = context.Queue()
        child = context.Process(target=_take_the_lock, args=(self.path, answer))
        child.start()
        try:
            verdict = answer.get(timeout=60)
        finally:
            child.join(timeout=60)
        self.assertEqual(child.exitcode, 0)
        return verdict

    def test_a_second_process_cannot_take_a_held_lock(self):
        filelock.lock_nb(self.fd)
        self.assertEqual(self._second_process(), "refused")

    def test_the_lock_is_free_again_once_it_is_released(self):
        filelock.lock_nb(self.fd)
        filelock.unlock(self.fd)
        self.assertEqual(self._second_process(), "taken")

    def test_the_lock_outlives_a_holder_record_written_through_it(self):
        """onelane writes its 512-byte record at offset 0 through this descriptor.

        Windows locks a byte range from wherever the descriptor is sitting, so the write
        moves the position the unlock would otherwise use. The lock has to hold across
        the write and still come off cleanly afterwards.
        """
        filelock.lock_nb(self.fd)
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.write(self.fd, b" " * 512)
        self.assertEqual(self._second_process(), "refused")
        filelock.unlock(self.fd)
        self.assertEqual(self._second_process(), "taken")

    def test_neither_module_reaches_for_fcntl_by_hand_again(self):
        from lite import onelane, server
        self.assertIs(server.lock_nb, filelock.lock_nb)
        self.assertIs(onelane.filelock, filelock)
        self.assertEqual(onelane.O_NOFOLLOW, filelock.O_NOFOLLOW)
        # The 0.1.16 bug in one line: a bare `import fcntl` at the top of either module
        # is a ModuleNotFoundError on Windows before a single lock is ever reached.
        for module in (server, onelane):
            self.assertFalse(hasattr(module, "fcntl"),
                             module.__name__ + " imports fcntl directly again")


if __name__ == "__main__":
    unittest.main()
