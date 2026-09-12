"""Detect the supplied full purification glow, anchored on its central icon."""
from pathlib import Path
import sys


class LimboDetector:
    def __init__(self, assets=None):
        import cv2
        import numpy as np
        from PIL import Image
        assets = assets or Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'limbo'
        reference = np.asarray(Image.open(assets / 'normal.png').convert('RGB'))
        self.icon = cv2.cvtColor(reference[174:227,178:231],cv2.COLOR_RGB2GRAY)

    def inspect(self, image):
        import cv2
        import numpy as np
        from PIL import Image
        # Normalize large captures; each screen may use a different UI scale.
        factor = min(1,720/max(image.size))
        rgb = np.asarray(image.convert('RGB').resize((round(image.width*factor),round(image.height*factor)),Image.Resampling.LANCZOS))
        gray = cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        best = (-1,None,None)
        for size in sorted(set([53]+[round(53*s) for s in np.geomspace(.35,3.0,38)])):
            if size >= min(gray.shape) or size < 15:
                continue
            template = cv2.resize(self.icon,(size,size),interpolation=cv2.INTER_AREA if size<53 else cv2.INTER_CUBIC)
            scores = cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED)
            _,score,_,position = cv2.minMaxLoc(scores)
            if score > best[0]:
                best=(score,position,size)
        score,position,size = best
        if score < .76:
            return None, {'icon_score':float(score),'reason':'icon_missing'}
        cx,cy = position[0]+size/2,position[1]+size/2
        # Require the sphere surrounding the icon to be visible, not a crop of
        # the icon alone or its skill-bar copy.
        radius = size*1.95
        if cx-radius<0 or cy-radius<0 or cx+radius>=rgb.shape[1] or cy+radius>=rgb.shape[0]:
            return None, {'icon_score':float(score),'reason':'sphere_clipped'}
        yy,xx=np.indices(rgb.shape[:2])
        distance=np.sqrt((xx-cx)**2+(yy-cy)**2)/size
        ring=(distance>.70)&(distance<1.55)
        pixels=rgb[ring].astype(float)
        red,green,blue=pixels.T
        cyan=(green>165)&(blue>175)&(green>red*1.03)&(blue>red*.98)
        glow=float(cyan.mean())
        # A bright inner sphere also occurs before completion. Require the
        # upper outer rim to be filled on the left, center AND right.
        dx=(xx-cx)/size
        dy=(yy-cy)/size
        upper=(distance>1.55)&(distance<1.9)&(dy<-.4)
        outer=[]
        for left,right in ((-3,-.5),(-.5,.5),(.5,3)):
            area=rgb[upper&(dx>=left)&(dx<right)].astype(float)
            r,g,b=area.T
            outer.append(float(((g>165)&(b>175)&(g>r*1.03)&(b>r*.98)).mean()))
        full=bool(glow>=.92 and min(outer)>=.88 and np.median(green)>185 and np.median(blue)>190)
        return full, {'icon_score':float(score),'glow':glow,'upper_fill':outer,'reason':'full' if full else 'charging'}


class StableFull:
    def __init__(self, frames=3):
        self.frames=frames
        self.candidate=None
        self.count=0

    def update(self, value):
        if value is None:
            self.candidate=None
            self.count=0
            return None
        if value != self.candidate:
            self.candidate=value
            self.count=1
        else:
            self.count+=1
        return value if self.count>=self.frames else None
