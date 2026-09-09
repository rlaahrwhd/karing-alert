import unittest
from logic import advice, parse_number, StableReadings, Cooldown, validate_thresholds, assign_gauge_numbers, spoken_advice


class Rules(unittest.TestCase):
    def test_spatial_assignment(self):
        points = [(120,220,185,None), (840,135,20,None), (540,50,180,None)]
        mapped = assign_gauge_numbers(points)
        self.assertEqual({n:p[0] for n,p in mapped.items()}, {'혼돈':840,'도올':540,'궁기':120})

    def test_ambiguous_gauge_is_rejected(self):
        self.assertIsNone(assign_gauge_numbers([(500,10,10,None)]))
        self.assertIsNone(assign_gauge_numbers([(500,10,10,None),(500,50,10,None),(500,100,10,None)]))
        self.assertIsNone(assign_gauge_numbers([(500,10,10,None)]*4))

    def test_custom_thresholds(self):
        high, low = validate_thresholds('900', '200')
        for value, triggered in [(899, False), (900, True), (201, False), (200, True)]:
            key, _ = advice({'혼돈':value, '도올':500, '궁기':500}, high=high, low=low)
            self.assertEqual(key is not None, triggered)

    def test_invalid_thresholds(self):
        for high, low in [('abc', 100), (800, -1), (1001, 100), (100, 100), (100, 200), (800.5, 100), ('', 100), (True, 0)]:
            with self.assertRaises(ValueError):
                validate_thresholds(high, low)
        self.assertEqual(validate_thresholds(1000, 0), (1000, 0))

    def test_all_directions(self):
        for name, high_color, low_color in [('혼돈','빨간','노란'), ('도올','노란','초록'), ('궁기','초록','빨간')]:
            for value, color in [(800, high_color), (100, low_color)]:
                values = dict.fromkeys(('혼돈','도올','궁기'), 500)
                values[name] = value
                self.assertIn(color+'실 맞아줘요.', advice(values)[1])

    def test_boundaries(self):
        for value in (101, 799):
            self.assertIsNone(advice({'혼돈':value,'도올':500,'궁기':500})[0])
        for value in (0,1000):
            self.assertEqual(advice({'혼돈':value,'도올':500,'궁기':500})[0][0], 'end')

    def test_unreadable(self):
        self.assertIsNone(advice({'혼돈':900,'도올':None,'궁기':500})[0])
        for text in ('5OO','1001','-1','80%','8 00',''):
            self.assertIsNone(parse_number(text,.99))
        self.assertIsNone(parse_number('800', .8))
        self.assertEqual(parse_number('800',.99), 800)

    def test_stability_and_stale(self):
        tracker = StableReadings()
        raw = dict.fromkeys(('혼돈','도올','궁기'),500)
        self.assertIsNone(tracker.update(raw)['혼돈'])
        tracker.update(raw)
        self.assertEqual(tracker.update(raw)['혼돈'],500)
        self.assertIsNone(tracker.update({**raw,'혼돈':900})['혼돈'])
        self.assertIsNone(tracker.update({**raw,'혼돈':None})['혼돈'])
        self.assertIsNone(tracker.update(raw)['혼돈'])

    def test_cooldown(self):
        gate = Cooldown()
        self.assertFalse(gate.allow(None,0))
        self.assertTrue(gate.allow('a',0))
        self.assertFalse(gate.allow('b',9))
        self.assertTrue(gate.allow('a',10))

    def test_phase(self):
        values = {'혼돈':500,'도올':500,'궁기':800}
        for phase in (1,2,3):
            key, text = advice(values,phase)
            self.assertEqual(spoken_advice(key,text), '초록실 맞아줘요.')
            for location in ('왼쪽','중앙','오른쪽'):
                self.assertNotIn(location,text)

    def test_phase_one_has_thread_without_location(self):
        for name in ('혼돈', '도올', '궁기'):
            for value in (800, 100):
                values = dict.fromkeys(('혼돈', '도올', '궁기'), 500)
                values[name] = value
                key, text = advice(values,1)
                self.assertIsNotNone(key)
                self.assertIn('실 맞아줘요',text)
                for location in ('왼쪽','중앙','오른쪽'):
                    self.assertNotIn(location,text)

    def test_conflicting_gauges(self):
        key, text = advice({'혼돈':900,'도올':900,'궁기':900})
        self.assertEqual(key[0], 'conflict')
        self.assertNotIn('맞아주세요',text)


if __name__ == '__main__':
    unittest.main()
