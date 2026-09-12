"""Numeric five-field cron in local time, with traditional DOM/DOW OR semantics."""
from datetime import datetime, timedelta


class Cron:
    def __init__(self, schedule):
        if not isinstance(schedule, str) or len(schedule.split()) != 5:
            raise ValueError('Expected five fields')
        self.fields = schedule.split()
        self.values = []
        for field, (low, high) in zip(self.fields, ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))):
            values = set()
            for part in field.split(','):
                bits = part.split('/')
                if len(bits) > 2 or (len(bits) == 2 and (not bits[1].isascii() or not bits[1].isdecimal())):
                    raise ValueError('Invalid step')
                step = int(bits[1]) if len(bits) == 2 else 1
                if not 1 <= step <= high + 1:
                    raise ValueError('Invalid step')
                if bits[0] == '*':
                    start, end = low, high
                else:
                    bounds = bits[0].split('-')
                    if len(bounds) not in (1, 2) or any(not b.isascii() or not b.isdecimal() for b in bounds):
                        raise ValueError('Invalid range')
                    start = int(bounds[0])
                    end = int(bounds[-1]) if len(bounds) == 2 else (high if len(bits) == 2 else start)
                    if not low <= start <= end <= high:
                        raise ValueError('Out of range')
                values.update(range(start, end + 1, step))
            self.values.append(values)
        if 7 in self.values[4]:
            self.values[4].add(0)
        self.schedule = ' '.join(self.fields)

    def matches(self, when):
        minute, hour, dom, month, dow = self.values
        day = when.day in dom
        weekday = (when.weekday() + 1) % 7 in dow
        # A wildcard day field constrains the other; two restricted fields are OR.
        days = (day and weekday) if any(f.startswith('*') for f in (self.fields[2], self.fields[4])) else (day or weekday)
        return when.minute in minute and when.hour in hour and when.month in month and days

    def next_after(self, timestamp):
        """Strictly future epoch seconds, or None for an impossible calendar date.

        Search days first to keep sparse schedules inexpensive. Epoch round trips
        skip nonexistent local times and preserve both occurrences of a DST fold.
        """
        first = datetime.fromtimestamp(timestamp).date()
        for offset in range(366 * 8):
            day = first + timedelta(days=offset)
            candidates = []
            for hour in sorted(self.values[1]):
                for minute in sorted(self.values[0]):
                    wall = datetime(day.year, day.month, day.day, hour, minute)
                    if not self.matches(wall):
                        continue
                    for fold in (0, 1):
                        stamp = wall.replace(fold=fold).timestamp()
                        if stamp > timestamp and datetime.fromtimestamp(stamp) == wall:
                            candidates.append(stamp)
            if candidates:
                return min(candidates)
        return None
