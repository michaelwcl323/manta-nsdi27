import unittest
from collections import OrderedDict

from benchmark.config import Committee, ConfigError


class CoreGroupConfigTests(unittest.TestCase):
    def committee(self, coverage, core_size=5, enabled=True):
        addresses = OrderedDict(
            (str(i), ['127.0.0.1', '127.0.0.1']) for i in range(10)
        )
        return Committee(
            addresses, 5000, 1, 2, coverage, coverage,
            attack_enabled=enabled, attack_group_size=core_size,
        )

    def test_rejects_core_that_exceeds_visibility_budget(self):
        with self.assertRaisesRegex(ConfigError, 'must be at least 6'):
            self.committee(5)

    def test_coverage_four_uses_three_core_authors_plus_self(self):
        committee = self.committee(4)
        self.assertEqual(committee.json['coverage'], 4)

    def test_accepts_core_plus_other_recipient(self):
        committee = self.committee(6)
        self.assertEqual(committee.json['attack_group_size'], 5)
        self.assertEqual(committee.json['coverage'], 6)

    def test_smaller_coverage_works_with_smaller_core(self):
        self.assertEqual(self.committee(4, 3).json['attack_group_size'], 3)

    def test_default_core_uses_half_the_committee(self):
        with self.assertRaisesRegex(ConfigError, 'core_group_size=5'):
            self.committee(5, 0)
        self.committee(6, 0)

    def test_disabled_attack_keeps_existing_configuration_valid(self):
        self.committee(4, enabled=False)


if __name__ == '__main__':
    unittest.main()
