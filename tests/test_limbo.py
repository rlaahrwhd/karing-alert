from pathlib import Path
import unittest
from PIL import Image,ImageEnhance,ImageOps
from limbo import LimboDetector,StableFull
from logic import voice_clip,Cooldown

ASSETS=Path(__file__).resolve().parents[1]/'assets'/'limbo'


class Limbo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector=LimboDetector(ASSETS)

    def test_references_at_different_scales(self):
        for name,expected in [('normal',False),('full',True)]:
            im=Image.open(ASSETS/f'{name}.png')
            for scale in (.65,1,1.5):
                picture=im.resize((round(im.width*scale),round(im.height*scale)))
                self.assertIs(self.detector.inspect(picture)[0],expected,(name,scale))

    def test_dimmed_and_padded_capture(self):
        for name,expected in [('normal',False),('full',True)]:
            im=Image.open(ASSETS/f'{name}.png')
            self.assertIs(self.detector.inspect(ImageEnhance.Brightness(im).enhance(.85))[0],expected)
            self.assertIs(self.detector.inspect(ImageOps.expand(im,border=40,fill='black'))[0],expected)

    def test_missing_or_clipped_gauge_does_not_alert(self):
        for color in ('black','white','cyan'):
            self.assertIsNone(self.detector.inspect(Image.new('RGB',(420,350),color))[0])
        im=Image.open(ASSETS/'normal.png').crop((165,160,240,238))
        self.assertIsNone(self.detector.inspect(im)[0])

    def test_bright_inner_sphere_without_full_upper_rim(self):
        import numpy as np
        im=np.array(Image.open(ASSETS/'full.png').convert('RGB'))
        yy,xx=np.indices(im.shape[:2])
        dx=(xx-199.5)/53
        dy=(yy-207.5)/53
        radius=np.hypot(dx,dy)
        # Keep the full reference's bright interior and icon, but empty one
        # section of its upper rim, simulating incomplete charging.
        for left,right in ((-3,-.5),(-.5,.5),(.5,3)):
            partial=im.copy()
            partial[(radius>1.55)&(radius<1.9)&(dy<-.4)&(dx>=left)&(dx<right)]=(25,70,100)
            self.assertIs(self.detector.inspect(Image.fromarray(partial))[0],False)

    def test_five_frame_confirmation_rejects_short_flash(self):
        stable=StableFull(frames=5)
        for state in (True,True,True,True,False,True,True,True,True):
            self.assertIsNone(stable.update(state))
        self.assertIs(stable.update(True),True)

    def test_transient_flash_and_lost_detection(self):
        stable=StableFull()
        for state in (False,True,False,True,None,True,True):
            self.assertIsNone(stable.update(state))
        self.assertIs(stable.update(True),True)
        self.assertIsNone(stable.update(None))
        self.assertIsNone(stable.update(True))

    def test_normal_full_transition_and_repeat_interval(self):
        stable=StableFull()
        for state in (False,False):
            self.assertIsNone(stable.update(state))
        self.assertIs(stable.update(False),False)
        for state in (True,True):
            self.assertIsNone(stable.update(state))
        self.assertIs(stable.update(True),True)
        self.assertEqual(voice_clip('충전 완료'),'limbo')
        self.assertTrue((ASSETS.parent/'voice'/'limbo.wav').is_file())
        gate=Cooldown(10)
        self.assertTrue(gate.allow(('limbo',),0))
        self.assertFalse(gate.allow(('limbo',),1))
        self.assertTrue(gate.allow(('limbo',),10))
