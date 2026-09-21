import tempfile
import unittest
from pathlib import Path

from benchmark.logs import LogParser, _to_posix_utc, parse_primary_log_markers


class LogTimestampTests(unittest.TestCase):
    def test_primary_name_ending_in_z_does_not_extend_timestamp(self):
        timestamp = '2026-09-21T03:27:40.951Z'
        prefix = f'[{timestamp} INFO  config] '
        log = ''.join(prefix + line + '\n' for line in (
            'Header size set to 1000 B',
            'Max header delay set to 50 ms',
            'Garbage collection depth set to 200 rounds',
            'Sync retry delay set to 1000 ms',
            'Sync retry nodes set to 7 nodes',
            'Batch size set to 500000 B',
            'Max batch delay set to 50 ms',
        ))
        log += (
            f'[{timestamp} INFO  primary::primary] '
            'Primary fuot8lP0UAR3JV4Z successfully booted on 10.10.1.3\n'
        )
        parser = LogParser.__new__(LogParser)
        *_, ip, boot_ts = parser._parse_primaries(log)
        self.assertEqual(ip, '10.10.1.3')
        self.assertEqual(boot_ts, _to_posix_utc(timestamp))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'primary.log'
            path.write_text(log)
            markers = parse_primary_log_markers(path)
        self.assertEqual(markers['boot_ts'], boot_ts)


if __name__ == '__main__':
    unittest.main()
