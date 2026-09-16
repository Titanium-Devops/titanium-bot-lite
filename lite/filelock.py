"""One non-blocking whole-file lock that works on POSIX and on Windows alike.

server.py takes it so one data directory has one owner. onelane.py takes it so one
Tiiny has one caller. Both reached for fcntl directly, and `import fcntl` is the very
first thing Python cannot do on Windows, so the app stopped at import on a tester's
machine long before it got anywhere near a lock:

    File "...\\lite\\server.py", line 6, in <module>
        import fcntl
    ModuleNotFoundError: No module named 'fcntl'

Both callers already recognise a refused lock the same way. POSIX flock raises
BlockingIOError, whose errno is EAGAIN or EACCES; onelane tests that errno directly and
server.py catches the exception type. msvcrt reports the same condition with errnos of
its own, so everything here funnels into BlockingIOError(EAGAIN) and every handler
already in the tree keeps working untouched.

The lock is advisory between processes that use THIS module, and the two platforms do
not interoperate with each other. That costs nothing here: a data directory and a Tiiny
are only ever shared by copies of the same program on the same machine.
"""
from __future__ import annotations

import contextlib
import errno
import os

# Windows locks a byte range, not a whole file, and that range lock is MANDATORY rather
# than advisory. onelane keeps a 512-byte holder record at offset 0 that other processes
# read while the lock is held, so locking byte 0 would turn every dashboard read into a
# lock violation. Put the locked byte comfortably past the record instead. It does not
# have to exist: Windows locks a region beyond end-of-file without complaint.
LOCK_BYTE = 4096

# Decide once, at import, so a platform with neither module says so here rather than at
# the first lock, halfway through starting up.
try:
    import fcntl
except ImportError:                       # Windows has msvcrt and no fcntl
    fcntl = None
    import msvcrt

# "Somebody else holds it" arrives under a different name on each platform, and not
# every name is defined on every platform, so collect whichever ones exist.
_BUSY = tuple({getattr(errno, name) for name in ("EACCES", "EAGAIN", "EDEADLK", "EDEADLOCK")
               if hasattr(errno, name)})


def _fd(handle):
    """Callers hold either a raw descriptor (onelane) or an open file (server.py)."""
    return handle if isinstance(handle, int) else handle.fileno()


@contextlib.contextmanager
def _at_lock_byte(fd):
    """msvcrt locks from wherever the descriptor happens to be sitting; put it back.

    onelane seeks to 0 and writes its holder record through this same descriptor, so a
    position left moved here would land the next record in the wrong place.
    """
    here = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, LOCK_BYTE, os.SEEK_SET)
    try:
        yield
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def lock_nb(handle):
    """Take the lock without waiting. Raises BlockingIOError when somebody else has it."""
    fd = _fd(handle)
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    with _at_lock_byte(fd):
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in _BUSY:
                raise BlockingIOError(errno.EAGAIN, "the lock is held by another process") from None
            raise


def unlock(handle):
    """Drop the lock. Closing the descriptor drops it on both platforms too."""
    fd = _fd(handle)
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    with _at_lock_byte(fd):
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            # Unlocking something we do not hold is silent under POSIX LOCK_UN, and
            # callers lean on that: onelane unlocks before re-opening a lock file whose
            # name moved out from under it. Keep the quiet behaviour here.
            pass


# os.open flags that only some platforms define. O_NOFOLLOW is a symlink defence and
# Windows has neither the flag nor the ambient symlink exposure it defends against, so
# falling back to 0 drops one bit from the mask and changes nothing else.
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
