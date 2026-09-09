import audioop
import io
from pathlib import Path
import unittest
import wave
from app import Speaker
from logic import advice, spoken_advice, voice_clip

VOICE = Path(__file__).resolve().parents[1] / 'assets' / 'voice'


class MaleVoice(unittest.TestCase):
    def test_every_alert_has_a_clip(self):
        for values in ({'혼돈':900,'도올':500,'궁기':500},
                       {'혼돈':500,'도올':900,'궁기':500},
                       {'혼돈':500,'도올':500,'궁기':900},
                       {'혼돈':1000,'도올':500,'궁기':500},
                       {'혼돈':900,'도올':900,'궁기':900}):
            key,text = advice(values)
            clip = voice_clip(spoken_advice(key,text))
            self.assertIsNotNone(clip)
            with wave.open(str(VOICE/f'{clip}.wav'),'rb') as source:
                self.assertGreater(source.getnframes(), 1000)

    def test_volume_scales_audio_without_changing_length(self):
        data = []
        for volume in (0,50,100):
            with wave.open(io.BytesIO(Speaker.clip_data(VOICE/'red.wav',volume)),'rb') as source:
                data.append(source.readframes(source.getnframes()))
        self.assertEqual(len(data[0]),len(data[2]))
        self.assertEqual(audioop.rms(data[0],2),0)
        self.assertAlmostEqual(audioop.rms(data[1],2)/audioop.rms(data[2],2),.5,places=2)
