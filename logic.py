"""Screen-independent alert rules."""
import re

NAMES = ('혼돈', '도올', '궁기')
# Thread -> (gauge increased, gauge decreased)
THREADS = {'노란': ('혼돈', '도올'), '초록': ('도올', '궁기'), '빨간': ('궁기', '혼돈')}
POSITIONS = {2: {'빨간': '왼쪽', '초록': '중앙', '노란': '오른쪽'},
             3: {'빨간': '왼쪽', '노란': '중앙', '초록': '오른쪽'}}


def validate_thresholds(high, low):
    if not re.fullmatch(r'[0-9]{1,4}', str(high)) or not re.fullmatch(r'[0-9]{1,4}', str(low)):
        raise ValueError('0~1000 사이의 정수를 입력해주세요.')
    high, low = int(high), int(low)
    if not 0 <= low < high <= 1000:
        raise ValueError('0 ≤ 하한 < 상한 ≤ 1000으로 설정해주세요.')
    return high, low


def parse_number(text, score):
    text = text.strip()
    if score < .85 or not re.fullmatch(r'[0-9]{1,4}', text):
        return None
    value = int(text)
    return value if 0 <= value <= 1000 else None


def assign_gauge_numbers(candidates):
    """Candidates: (value, center_x, center_y, box). Reject ambiguous layouts."""
    if len(candidates) != 3:
        return None
    top, a, b = sorted(candidates, key=lambda item: item[2])
    left, right = sorted((a, b), key=lambda item: item[1])
    span = right[1] - left[1]
    if span <= 0 or not left[1] + .15*span < top[1] < right[1] - .15*span:
        return None
    if min(left[2], right[2]) - top[2] < .3*span or abs(left[2]-right[2]) > .4*span:
        return None
    return {'혼돈': top, '도올': left, '궁기': right}


class StableReadings:
    """Require three consecutive valid frames, without retaining stale values."""
    def __init__(self):
        self.history = {name: [] for name in NAMES}

    def update(self, raw):
        values = {}
        for name in NAMES:
            value = raw.get(name)
            history = self.history[name]
            if value is None:
                history.clear()
                values[name] = None
                continue
            history.append(value)
            del history[:-3]
            # Reject isolated OCR jumps; ordinary changing readings need not match.
            values[name] = sorted(history)[1] if len(history) == 3 and max(history) - min(history) <= 120 else None
        return values


def advice(values, phase=3, high=800, low=100):
    if any(values.get(n) is None for n in NAMES):
        return None, '숫자 확인 중 · 세 게이지가 모두 인식되면 안내합니다.'
    extremes = [n for n in NAMES if values[n] in (0, 1000)]
    if extremes:
        names = ', '.join(extremes)
        return ('end', tuple(extremes)), f'{names} 게이지가 한계값이에요! 게이지 상태를 확인해주세요.'
    danger = [(n, 'high' if values[n] >= high else 'low') for n in NAMES
              if values[n] >= high or values[n] <= low]
    if not danger:
        return None, '안정 범위 · 게이지를 확인하고 있어요.'
    danger.sort(key=lambda x: min(values[x[0]], 1000-values[x[0]]))
    # Prefer a correction whose other affected gauge is not already endangered.
    candidates = []
    for name, direction in danger:
        color = next(c for c, pair in THREADS.items() if pair[1 if direction == 'high' else 0] == name)
        inc, dec = THREADS[color]
        other = inc if direction == 'high' else dec
        conflict = values[other] >= high if direction == 'high' else values[other] <= low
        candidates.append((conflict, name, direction, color, other))
    conflict, name, direction, color, other = min(candidates, key=lambda x: x[0])
    state = '높아요' if direction == 'high' else '낮아요'
    if conflict:
        return ('conflict', name, direction), f'{name} 게이지가 너무 {state}! {color} 실은 {other}도 위험하게 만들 수 있어요. 함께 확인해주세요.'
    return (name, direction, color), f'{name} 게이지가 너무 {state}! {color}실 맞아줘요.'


def spoken_advice(key, text):
    if key and key[0] not in ('conflict', 'end', 'error'):
        return f'{key[2]}실 맞아줘요.'
    return text


def voice_clip(text):
    colors = {'빨간실 맞아줘요.':'red', '초록실 맞아줘요.':'green', '노란실 맞아줘요.':'yellow'}
    if text in colors:
        return colors[text]
    if '한계값' in text:
        return 'limit'
    if '함께 확인' in text:
        return 'conflict'
    return None


class Cooldown:
    def __init__(self, seconds=10):
        self.seconds = seconds
        self.last = float('-inf')

    def allow(self, key, now):
        if key is None or now-self.last < self.seconds:
            return False
        self.last = now
        return True
