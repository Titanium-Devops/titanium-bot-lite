"""File-backed routines and a polling scheduler feeding the single turn worker."""
import json
import threading
import time

from .cron import Cron


def read_routines(root):
    rows = []
    for path in sorted((root / 'routines').glob('*/routine.json')):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        try:
            item = json.loads(path.read_text())
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in ('name', 'prompt', 'schedule')):
                continue
            Cron(item['schedule'])
            rows.append((path, item))
        except (OSError, ValueError, TypeError):
            continue  # One damaged owner-edited file must not stop other clocks.
    return rows


class Scheduler:
    def __init__(self, app):
        self.app = app
        self.next_runs = {}
        self.pending = set()
        self.refresh(time.time())
        self.thread = threading.Thread(target=self.run, name='Titan routines', daemon=True)

    def refresh(self, now):
        rows = read_routines(self.app.root)
        present = set()
        for path, item in rows:
            ident = path.parent.name
            if item.get('enabled') is not True:
                continue
            present.add(ident)
            signature = (item['schedule'], item.get('createdAt'))
            old = self.next_runs.get(ident)
            if old is None or old[0] != signature:
                self.next_runs[ident] = (signature, Cron(item['schedule']).next_after(now))
        for ident in self.next_runs.keys() - present:
            del self.next_runs[ident]
        return rows

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.app.lock:
            for path, item in self.refresh(now):
                ident = path.parent.name
                if ident not in self.next_runs:
                    continue
                signature, due = self.next_runs[ident]
                if due is None or due > now:
                    continue
                self.next_runs[ident] = (signature, Cron(item['schedule']).next_after(now))
                # Never replay earlier minutes or build a backlog of routine turns.
                if now - due >= 60 or ident in self.pending or self.app.jobs.full():
                    continue
                self.pending.add(ident)
                self.app.jobs.put_nowait(('routine', ident, due, signature))

    def run(self):
        while not self.app.stopping.wait(30):
            self.tick()
