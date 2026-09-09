import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

from logic import NAMES, StableReadings, Cooldown, advice, parse_number, validate_thresholds, assign_gauge_numbers, spoken_advice, voice_clip

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
CONFIG = BASE / 'settings.json'


def load_bundled_fonts():
    """Register bundled fonts for this process without installing system fonts."""
    assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'fonts'
    add_font = ctypes.windll.gdi32.AddFontResourceExW
    add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    add_font.restype = ctypes.c_int
    for name in ('Maplestory Light.ttf', 'Maplestory Bold.ttf'):
        font_path = assets / name
        if not font_path.is_file() or not add_font(str(font_path), 0x10, None):
            raise RuntimeError(f'메이플스토리 폰트를 불러올 수 없습니다: {font_path}')


def read_digits(engine, image):
    import numpy as np
    from PIL import ImageOps, Image
    # Recognition only: each user-selected crop must contain exactly one number.
    image = ImageOps.expand(image.convert('RGB').resize((image.width*4, image.height*4), Image.Resampling.LANCZOS), border=12, fill='black')
    result, _ = engine(np.asarray(image), use_det=False, use_cls=False, use_rec=True)
    if not result or len(result) != 1:
        return None
    return parse_number(str(result[0][0]), float(result[0][1]))


def read_gauge(engine, image):
    import numpy as np
    from PIL import ImageOps, Image
    scale = max(1, min(3, 900 / max(image.size)))
    enlarged = image.convert('RGB').resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
    padded = ImageOps.expand(enlarged, border=20, fill='black')
    results, _ = engine(np.asarray(padded), use_det=True, use_cls=False, use_rec=True)
    candidates = []
    for box, text, score in results or []:
        value = parse_number(str(text), float(score))
        if value is None:
            continue
        xs = [(float(point[0])-20)/scale for point in box]
        ys = [(float(point[1])-20)/scale for point in box]
        crop_box = (max(0,int(min(xs))-3), max(0,int(min(ys))-3), min(image.width,int(max(xs))+4), min(image.height,int(max(ys))+4))
        candidates.append((value, sum(xs)/4, sum(ys)/4, crop_box))
    mapped = assign_gauge_numbers(candidates)
    if mapped is None:
        return dict.fromkeys(NAMES), {}
    return ({name:item[0] for name,item in mapped.items()},
            {name:image.crop(item[3]) for name,item in mapped.items()})


class Speaker:
    def __init__(self):
        self.busy = False
        self.error = None

    @staticmethod
    def clip_data(path, volume):
        import audioop
        import io
        import wave
        with wave.open(str(path), 'rb') as source:
            params = source.getparams()
            pcm = source.readframes(source.getnframes())
        pcm = audioop.mul(pcm, params.sampwidth, max(0,min(100,int(volume)))/100)
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as output:
            output.setparams(params)
            output.writeframes(pcm)
        return buffer.getvalue()

    @staticmethod
    def play_clip(path, volume):
        import winsound
        winsound.PlaySound(Speaker.clip_data(path, volume), winsound.SND_MEMORY | winsound.SND_NODEFAULT)

    def speak(self, text, volume=100):
        volume = max(0, min(100, int(volume)))
        if volume == 0 or self.busy:
            return
        clip = voice_clip(text)
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        path = assets / 'assets' / 'voice' / f'{clip}.wav'
        if clip is None or not path.is_file():
            self.error = '남성 안내음 파일을 찾을 수 없어요. 압축을 모두 풀었는지 확인해주세요.'
            return
        self.busy = True
        def run():
            try:
                self.play_clip(path, volume)
            except Exception:
                self.error = '남성 안내음 재생에 실패했어요. 출력 장치와 음성 파일을 확인해주세요.'
            finally:
                self.busy = False
        threading.Thread(target=run, daemon=True).start()


class Toggle(tk.Canvas):
    def __init__(self, parent, app, text, variable, command):
        super().__init__(parent, highlightthickness=0, takefocus=True, cursor='hand2')
        self.app, self.text, self.variable, self.command = app, text, variable, command
        self.bind('<Button-1>', self.toggle)
        self.bind('<space>', self.toggle)
        self.bind('<Return>', self.toggle)
        self.bind('<FocusIn>', lambda e: self.draw())
        self.bind('<FocusOut>', lambda e: self.draw())
        self.variable.trace_add('write', lambda *args: self.draw())

    def toggle(self, event=None):
        self.focus_set()
        self.variable.set(not self.variable.get())
        self.command()
        return 'break'

    def draw(self):
        if not hasattr(self.app, 'colors'):
            return
        c = self.app.colors
        enabled = self.variable.get()
        factor = self.app.font_scale / 100
        font = self.app.ui_font(10)
        label = f'{self.text}  {"켜짐" if enabled else "꺼짐"}'
        width, height = round(44*factor), round(24*factor)
        self.configure(bg=c['bg'], width=width+16+font.measure(label), height=height+10)
        self.delete('all')
        x, y, r = 2, 5, height/2
        track = '#f5f7fa' if enabled else c['card']
        edge = c['accent'] if self.focus_get() == self else c['border']
        self.create_line(x+r,y+r,x+width-r,y+r,fill=edge,width=height+2,capstyle=tk.ROUND)
        self.create_line(x+r,y+r,x+width-r,y+r,fill=track,width=height,capstyle=tk.ROUND)
        knob_x = x+width-height+3 if enabled else x+3
        self.create_oval(knob_x,y+3,knob_x+height-6,y+height-3,
                         fill='#20262f' if enabled else '#424b58', outline='')
        self.create_text(width+12,y+r,text=label,anchor='w',font=font,
                         fill=c['text'] if enabled else c['muted'])


class App:
    def __init__(self, root):
        self.root = root
        root.title('카링 알림이')
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        root.iconbitmap(str(assets / 'assets' / 'karing.ico'))
        try:
            self.font_dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id()) or 96
        except Exception:
            self.font_dpi = 96
        root.tk.call('tk', 'scaling', self.font_dpi / 72)
        root.geometry(f'840x{min(820, root.winfo_screenheight()-90)}')
        root.minsize(790, 620)
        self.gauge_region = None
        self.events = queue.Queue(maxsize=3)
        self.stop = threading.Event()
        self.stop.set()
        self.worker = None
        self.speaker = Speaker()
        self.gate = Cooldown()
        self.voice = tk.BooleanVar(value=True)
        self.volume = tk.IntVar(value=80)
        self.volume_label = tk.StringVar(value='80%')
        self.topmost = tk.BooleanVar(value=True)
        self.phase = tk.StringVar(value='3')
        self.font_scale = 100
        self.font_scale_input = tk.StringVar(value='100%')
        self.font_objects = {}
        self.toggles = []
        self.theme = tk.StringVar(value='dark')
        self.high, self.low = 800, 100
        self.high_input = tk.StringVar(value='800')
        self.low_input = tk.StringVar(value='100')
        self.threshold_note = tk.StringVar()
        self.status = tk.StringVar(value='게이지 전체를 한 번 지정한 뒤 모니터링을 시작하세요.')
        self.message = tk.StringVar(value='게이지를 읽을 준비가 됐어요.')
        self.labels, self.images, self.bars = {}, {}, {}
        self.current_values = dict.fromkeys(NAMES)
        self.alert_key = None
        self.settings_load()
        families = set(tkfont.families(root))
        self.font = next((f for f in ('Maplestory', '메이플스토리') if f in families), 'Maplestory')
        self.style = ttk.Style()
        self.style.theme_use('clam')
        root.option_add('*Font', self.ui_font(10))
        self.scroll = tk.Canvas(root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient='vertical', command=self.scroll.yview)
        scrollbar.pack(side='right', fill='y')
        self.scroll.pack(side='left', fill='both', expand=True)
        self.scroll.configure(yscrollcommand=scrollbar.set)
        frame = ttk.Frame(self.scroll, padding=24)
        window = self.scroll.create_window(0, 0, anchor='nw', window=frame)
        frame.bind('<Configure>', lambda e: self.scroll.configure(scrollregion=self.scroll.bbox('all')))
        self.scroll.bind('<Configure>', lambda e: self.scroll.itemconfigure(window, width=e.width))
        def wheel(event):
            if not isinstance(event.widget, (ttk.Spinbox, ttk.Combobox)):
                self.scroll.yview_scroll(-int(event.delta/120), 'units')
        root.bind('<MouseWheel>', wheel)
        header = ttk.Frame(frame)
        header.pack(fill='x')
        brand = ttk.Frame(header)
        brand.pack(side='left')
        ttk.Label(brand, text='KARING  /  GAUGE MONITOR', style='Eyebrow.TLabel').pack(anchor='w')
        ttk.Label(brand, text='카링 알림이', style='Title.TLabel').pack(anchor='w', pady=(3, 0))
        modes = ttk.Frame(header)
        modes.pack(side='right', anchor='n', pady=5)
        for text, value in [('라이트', 'light'), ('다크', 'dark')]:
            ttk.Radiobutton(modes, text=text, value=value, variable=self.theme,
                            style='Mode.TRadiobutton', command=self.change_theme).pack(side='left', padx=2)
        ttk.Label(frame, text='게이지는 한눈에, 실 안내는 필요한 순간에.', style='Muted.TLabel').pack(anchor='w', pady=(5, 18))

        region_row = ttk.Frame(frame)
        region_row.pack(fill='x', pady=(0,12))
        ttk.Label(region_row, text='위 혼돈 · 왼쪽 도올 · 오른쪽 궁기', style='Muted.TLabel').pack(side='left')
        self.region_button = ttk.Button(region_row, text='게이지 전체 영역 지정', command=self.select)
        self.region_button.pack(side='right')
        gauges = ttk.Frame(frame)
        gauges.pack(fill='x')
        for index, name in enumerate(NAMES):
            gauges.columnconfigure(index, weight=1, uniform='gauge')
            card = ttk.Frame(gauges, style='Card.TFrame', padding=16)
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 6, 0 if index == 2 else 6))
            ttk.Label(card, text=name, style=f'{name}.TLabel').pack(anchor='w')
            self.labels[name] = ttk.Label(card, text='—', style='Number.TLabel')
            self.labels[name].pack(anchor='w', pady=(2, 0))
            self.bars[name] = ttk.Progressbar(card, maximum=1000, style=f'{name}.Horizontal.TProgressbar')
            self.bars[name].pack(fill='x', pady=(3, 8))
            preview_row = ttk.Frame(card, style='InnerCard.TFrame', height=27)
            preview_row.pack(fill='x', pady=(0, 6))
            preview_row.pack_propagate(False)
            self.images[name] = ttk.Label(preview_row, text='인식 대기', style='CardMuted.TLabel')
            self.images[name].pack(side='left')

        config = ttk.Frame(frame, style='Card.TFrame', padding=16)
        config.pack(fill='x', pady=(16, 12))
        top = ttk.Frame(config, style='InnerCard.TFrame')
        top.pack(fill='x')
        ttk.Label(top, text='알림 조건', style='Section.TLabel').pack(side='left')
        ttk.Label(top, text='세 게이지 공통 · 음성 간격 10초', style='CardMuted.TLabel').pack(side='right')
        inputs = ttk.Frame(config, style='InnerCard.TFrame')
        inputs.pack(fill='x', pady=(12, 10))
        ttk.Label(inputs, text='게이지', style='Card.TLabel').pack(side='left')
        high = ttk.Spinbox(inputs, from_=1, to=1000, textvariable=self.high_input, width=6, font=self.ui_font(12))
        high.pack(side='left', padx=(10, 7))
        ttk.Label(inputs, text='이상  또는', style='Card.TLabel').pack(side='left')
        low = ttk.Spinbox(inputs, from_=0, to=999, textvariable=self.low_input, width=6, font=self.ui_font(12))
        low.pack(side='left', padx=(12, 7))
        ttk.Label(inputs, text='이하일 때 알림', style='Card.TLabel').pack(side='left')
        ttk.Button(inputs, text='설정 적용', style='Accent.TButton', command=self.apply_thresholds).pack(side='right')
        high.bind('<Return>', lambda e: self.apply_thresholds())
        low.bind('<Return>', lambda e: self.apply_thresholds())
        ttk.Label(config, textvariable=self.threshold_note, style='CardMuted.TLabel').pack(anchor='w')

        options = ttk.Frame(frame)
        options.pack(fill='x', pady=(0, 12))
        ttk.Label(options, text='페이즈', style='Muted.TLabel').pack(side='left')
        combo = ttk.Combobox(options, textvariable=self.phase, values=['1', '2', '3'], state='readonly', width=3)
        combo.pack(side='left', padx=(8, 22))
        combo.bind('<<ComboboxSelected>>', lambda e: self.preference_changed())
        ttk.Label(options, text='글자 크기', style='Muted.TLabel').pack(side='left')
        font_picker = ttk.Combobox(options, textvariable=self.font_scale_input, values=['80%','90%','100%','110%','120%','130%'], state='readonly', width=6)
        font_picker.pack(side='left', padx=(8,0))
        font_picker.bind('<<ComboboxSelected>>', lambda e: self.change_font_scale())
        ttk.Button(options, text='음성 테스트', command=lambda: self.speaker.speak('빨간실 맞아줘요.', self.volume.get())).pack(side='right')

        toggle_row = ttk.Frame(frame)
        toggle_row.pack(fill='x', pady=(0,12))
        for text, variable, callback in [('음성 알림',self.voice,self.settings_save), ('항상 위에 표시',self.topmost,self.set_top)]:
            switch = Toggle(toggle_row, self, text, variable, callback)
            switch.pack(side='left', padx=(0,24))
            self.toggles.append(switch)
        volume_row = ttk.Frame(frame)
        volume_row.pack(fill='x', pady=(0,12))
        ttk.Label(volume_row, text='음성 음량 · 남성', style='Muted.TLabel').pack(side='left', padx=(0,12))
        volume_slider = ttk.Scale(volume_row, from_=0, to=100, variable=self.volume, command=self.volume_changed)
        volume_slider.pack(side='left', fill='x', expand=True)
        ttk.Label(volume_row, textvariable=self.volume_label, width=6, anchor='e', style='Muted.TLabel').pack(side='left', padx=(12,0))
        self.volume_label.set(f'{self.volume.get()}%')
        self.alert = tk.Label(frame, textvariable=self.message, font=self.ui_font(14, True),
                              wraplength=650, justify='left', anchor='w', padx=18, pady=15)
        self.alert.pack(fill='x')
        ttk.Label(frame, textvariable=self.status, style='Muted.TLabel', wraplength=760).pack(fill='x', pady=(7, 10))
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='모니터링 시작', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left', expand=True, fill='x')
        ttk.Button(actions, text='모니터링 종료', command=self.pause).pack(side='left', expand=True, fill='x', padx=(10, 0))
        ttk.Label(frame, text='세 숫자가 모두 보이도록 게이지 전체를 지정하세요. 화면이 이동하면 다시 지정해주세요.', style='Foot.TLabel').pack(anchor='w', pady=(12, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.apply_theme()
        self.update_threshold_note()
        self.change_font_scale()
        self.set_top()
        root.after(100, self.poll)

    def ui_font(self, size, bold=False):
        key = (size, bold)
        if key not in self.font_objects:
            self.font_objects[key] = tkfont.Font(root=self.root, family=self.font,
                size=self.font_pixels(size), weight='bold' if bold else 'normal')
        return self.font_objects[key]

    def font_pixels(self, size):
        # Integer device pixels avoid rounding small point sizes at fractional DPI.
        return -max(10, round(max(size, 10.5)*self.font_dpi/72*self.font_scale/100))

    def change_font_scale(self):
        self.font_scale = int(self.font_scale_input.get().rstrip('%'))
        for (size, bold), font in self.font_objects.items():
            font.configure(size=self.font_pixels(size))
        for switch in self.toggles:
            switch.draw()
        width = min(round(790*self.font_scale/100), self.root.winfo_screenwidth()-60)
        self.root.minsize(max(790,width), 620)
        self.settings_save()

    def apply_theme(self):
        dark = self.theme.get() == 'dark'
        self.colors = c = ({'bg':'#0a0e14', 'card':'#111821', 'field':'#0c121b', 'border':'#293544',
            'text':'#edf3fb', 'muted':'#95a5bb', 'accent':'#5ad6f5', 'hover':'#223344',
            'danger':'#ff9187', 'alert':'#182b35', 'danger_bg':'#382128'} if dark else
            {'bg':'#f3f6fa', 'card':'#ffffff', 'field':'#f7f9fc', 'border':'#d7e0eb',
            'text':'#17283e', 'muted':'#61748c', 'accent':'#087f9d', 'hover':'#e4edf5',
            'danger':'#b63537', 'alert':'#e1f2f7', 'danger_bg':'#fce8e7'})
        st = self.style
        self.root.configure(bg=c['bg'])
        self.scroll.configure(bg=c['bg'])
        st.configure('.', font=self.ui_font(10), background=c['bg'], foreground=c['text'], bordercolor=c['border'], lightcolor=c['border'], darkcolor=c['border'])
        st.configure('TFrame', background=c['bg'])
        st.configure('TLabel', background=c['bg'], foreground=c['text'])
        st.configure('Muted.TLabel', foreground=c['muted'])
        st.configure('Foot.TLabel', foreground=c['muted'], font=self.ui_font(9))
        st.configure('Eyebrow.TLabel', foreground=c['accent'], font=self.ui_font(9, True))
        st.configure('Title.TLabel', font=self.ui_font(25, True))
        st.configure('Card.TFrame', background=c['card'], relief='solid', borderwidth=1)
        st.configure('InnerCard.TFrame', background=c['card'], relief='flat', borderwidth=0)
        st.configure('Card.TLabel', background=c['card'])
        st.configure('CardMuted.TLabel', background=c['card'], foreground=c['muted'], font=self.ui_font(9))
        st.configure('Section.TLabel', background=c['card'], font=self.ui_font(11, True))
        st.configure('Number.TLabel', background=c['card'], foreground=c['text'], font=self.ui_font(28, True))
        st.configure('TButton', background=c['card'], foreground=c['text'], padding=(12, 8), relief='flat', borderwidth=1)
        st.map('TButton', background=[('active',c['hover']),('pressed',c['hover'])], foreground=[('disabled',c['muted'])])
        st.configure('Accent.TButton', background=c['accent'], foreground='#07131c' if dark else '#ffffff', font=self.ui_font(10, True))
        st.map('Accent.TButton', background=[('disabled',c['border']),('active','#83e5fc' if dark else '#096e86')], foreground=[('disabled',c['muted'])])
        for kind in ('TSpinbox', 'TCombobox'):
            st.configure(kind, fieldbackground=c['field'], background=c['card'], foreground=c['text'], arrowcolor=c['accent'], padding=6, insertcolor=c['text'])
            st.map(kind, fieldbackground=[('readonly',c['field'])], foreground=[('readonly',c['text'])])
        self.root.option_add('*TCombobox*Listbox.background', c['card'])
        self.root.option_add('*TCombobox*Listbox.foreground', c['text'])
        st.configure('TCheckbutton', background=c['bg'], foreground=c['text'], indicatorbackground=c['field'])
        st.map('TCheckbutton', background=[('active',c['bg'])], indicatorbackground=[('selected',c['accent'])])
        st.configure('Mode.TRadiobutton', padding=(12,7), background=c['card'], foreground=c['muted'])
        st.layout('Mode.TRadiobutton', [('Radiobutton.padding', {'sticky':'nswe', 'children':[('Radiobutton.label', {'sticky':'nswe'})]})])
        st.map('Mode.TRadiobutton', background=[('selected',c['alert']),('active',c['hover'])], foreground=[('selected',c['accent'])])
        for name, color in zip(NAMES, ('#b69af7','#65d9b1','#f0c76a') if dark else ('#7951bb','#188461','#a66b08')):
            st.configure(f'{name}.TLabel', background=c['card'], foreground=color, font=self.ui_font(11, True))
            st.configure(f'{name}.Horizontal.TProgressbar', background=color, troughcolor=c['field'], bordercolor=c['card'], lightcolor=color, darkcolor=color, thickness=5)
        self.refresh_values()
        self.refresh_alert()
        for switch in self.toggles:
            switch.draw()

    def refresh_alert(self):
        self.alert.configure(bg=self.colors['danger_bg'] if self.alert_key else self.colors['alert'],
                             fg=self.colors['danger'] if self.alert_key else self.colors['text'])

    def refresh_values(self):
        for name, value in self.current_values.items():
            danger = value is not None and (value >= self.high or value <= self.low)
            self.labels[name].configure(text='—' if value is None else str(value), foreground=self.colors['danger'] if danger else self.colors['text'])
            self.bars[name]['value'] = 0 if value is None else value

    def volume_changed(self, value):
        volume = max(0, min(100, round(float(value))))
        self.volume.set(volume)
        self.volume_label.set(f'{volume}%' if volume else '음소거')
        self.settings_save()

    def change_theme(self):
        self.apply_theme()
        self.settings_save()

    def update_threshold_note(self):
        self.threshold_note.set(f'적용 중  ≥ {self.high}  /  ≤ {self.low}     ·     0~1000 사이, 하한은 상한보다 작게 입력')

    def apply_thresholds(self):
        try:
            high, low = validate_thresholds(self.high_input.get().strip(), self.low_input.get().strip())
        except ValueError as exc:
            messagebox.showerror('알림 조건 확인', str(exc), parent=self.root)
            return False
        self.high, self.low = high, low
        self.high_input.set(str(high))
        self.low_input.set(str(low))
        self.update_threshold_note()
        self.refresh_values()
        self.preference_changed()
        self.status.set(f'알림 기준을 저장했어요. {high} 이상 또는 {low} 이하일 때 알려드려요.')
        return True

    def preference_changed(self):
        if not self.stop.is_set():
            self.alert_key, text = advice(self.current_values, int(self.phase.get()), self.high, self.low)
            self.message.set(text)
            self.refresh_alert()
        self.settings_save()

    def set_top(self):
        self.root.attributes('-topmost', self.topmost.get())
        self.settings_save()

    def settings_load(self):
        try:
            data = json.loads(CONFIG.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return
            r = data.get('gauge_region')
            if isinstance(r, dict) and all(type(r.get(k)) is int for k in ('left','top','width','height')) and 60 <= r['width'] <= 2000 and 60 <= r['height'] <= 1500:
                self.gauge_region = r
            scale = data.get('font_scale', 100)
            self.font_scale = scale if type(scale) is int and 80 <= scale <= 130 else 100
            self.font_scale_input.set(f'{self.font_scale}%')
            volume = data.get('volume', 80)
            self.volume.set(max(0,min(100,volume)) if type(volume) is int else 80)
            self.phase.set(str(data.get('phase', 3)) if data.get('phase', 3) in (1, 2, 3) else '3')
            self.voice.set(bool(data.get('voice', True)))
            self.topmost.set(bool(data.get('topmost', True)))
            self.theme.set(data.get('theme') if data.get('theme') in ('dark', 'light') else 'dark')
            try:
                self.high, self.low = validate_thresholds(data.get('high', 800), data.get('low', 100))
            except ValueError:
                self.high, self.low = 800, 100
            self.high_input.set(str(self.high))
            self.low_input.set(str(self.low))
        except (OSError, ValueError, TypeError):
            pass

    def settings_save(self):
        try:
            CONFIG.write_text(json.dumps({'gauge_region': self.gauge_region, 'volume': self.volume.get(), 'font_scale': self.font_scale, 'phase': int(self.phase.get()), 'voice': self.voice.get(), 'topmost': self.topmost.get(), 'theme': self.theme.get(), 'high': self.high, 'low': self.low}, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            self.status.set(f'설정 저장 실패: {exc}')

    def select(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo('영역 지정', '모니터링을 종료한 후 영역을 지정해주세요.')
            return
        self.root.withdraw()
        self.root.after(250, self.selector)

    def selector(self):
        import mss
        from PIL import Image, ImageTk
        try:
            with mss.mss() as capture:
                monitor = capture.monitors[0]
                shot = capture.grab(monitor)
                picture = Image.frombytes('RGB', shot.size, shot.rgb)
            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.attributes('-topmost', True)
            overlay.geometry(f"{monitor['width']}x{monitor['height']}+0+0")
            overlay.update_idletasks()
            # Signed virtual desktop coordinates work for monitors left of primary.
            hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, monitor['left'], monitor['top'], monitor['width'], monitor['height'], 0x0040)
            canvas = tk.Canvas(overlay, highlightthickness=0, cursor='crosshair')
            canvas.pack(fill='both', expand=True)
            photo = ImageTk.PhotoImage(picture)
            canvas.create_image(0, 0, image=photo, anchor='nw')
            canvas.photo = photo
            canvas.create_rectangle(10, 10, 830, 60, fill='#101827', outline='')
            canvas.create_text(25, 34, text='세 숫자가 포함된 게이지 전체를 드래그하세요 · Esc 취소', fill='white', anchor='w', font=self.ui_font(15))
            start = []
            box = [None]
            def begin(event):
                start[:] = [event.x, event.y]
                if box[0]:
                    canvas.delete(box[0])
                box[0] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#00ffb3', width=3)
            def drag(event):
                if start:
                    canvas.coords(box[0], *start, event.x, event.y)
            def finish(event):
                if not start:
                    return
                x1, x2 = sorted((start[0], event.x))
                y1, y2 = sorted((start[1], event.y))
                if not (60 <= x2-x1 <= 2000 and 60 <= y2-y1 <= 1500):
                    return
                self.gauge_region = {'left': monitor['left']+x1, 'top': monitor['top']+y1, 'width': x2-x1, 'height': y2-y1}
                overlay.destroy()
                self.root.deiconify()
                self.region_button.configure(text='게이지 영역 다시 지정')
                self.settings_save()
                self.status.set('전체 영역 지정 완료. 위·왼쪽·오른쪽 숫자를 자동으로 구분합니다.')
            canvas.bind('<ButtonPress-1>', begin)
            canvas.bind('<B1-Motion>', drag)
            canvas.bind('<ButtonRelease-1>', finish)
            overlay.bind('<Escape>', lambda e: (overlay.destroy(), self.root.deiconify()))
            overlay.focus_force()
        except Exception as exc:
            self.root.deiconify()
            messagebox.showerror('화면 캡처 실패', str(exc))

    def start(self):
        if not self.apply_thresholds():
            return
        if self.gauge_region is None:
            messagebox.showinfo('영역 지정 필요', '세 숫자가 포함된 게이지 전체 영역을 한 번 지정해주세요.')
            return
        if self.worker and self.worker.is_alive():
            return
        while not self.events.empty():
            self.events.get_nowait()
        self.stop.clear()
        self.gate = Cooldown()
        self.settings_save()
        self.start_button.configure(state='disabled')
        self.status.set('OCR 준비 중… 처음 시작할 때 시간이 걸릴 수 있어요.')
        region = dict(self.gauge_region)
        self.worker = threading.Thread(target=self.monitor, args=(region,), daemon=True)
        self.worker.start()

    def emit(self, event):
        if self.events.full():
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
        self.events.put_nowait(event)

    def monitor(self, region):
        try:
            import mss
            from PIL import Image
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            stable = StableReadings()
            with mss.mss() as capture:
                while not self.stop.is_set():
                    started = time.monotonic()
                    shot = capture.grab(region)
                    frame = Image.frombytes('RGB', shot.size, shot.rgb)
                    raw, previews = read_gauge(engine, frame)
                    for crop in previews.values():
                        crop.thumbnail((100, 27))
                    self.emit(('values', time.monotonic(), stable.update(raw), previews))
                    self.stop.wait(max(.05, .5-(time.monotonic()-started)))
        except Exception as exc:
            self.emit(('error', str(exc)))

    def pause(self):
        self.stop.set()
        self.message.set('모니터링 종료')
        self.status.set('시작 버튼으로 다시 모니터링할 수 있어요.')
        self.current_values = dict.fromkeys(NAMES)
        self.alert_key = None
        self.refresh_values()
        self.refresh_alert()

    def poll(self):
        from PIL import ImageTk
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'error':
                    self.stop.set()
                    self.message.set('모니터링 오류 · 알림 중단')
                    self.status.set(event[1])
                    self.current_values = dict.fromkeys(NAMES)
                    self.alert_key = ('error',)
                    self.refresh_values()
                    self.refresh_alert()
                elif not self.stop.is_set():
                    _, timestamp, values, previews = event
                    if time.monotonic()-timestamp > 2:
                        continue
                    self.current_values = values
                    self.refresh_values()
                    for name in NAMES:
                        if name in previews:
                            picture = ImageTk.PhotoImage(previews[name])
                            self.images[name].configure(image=picture, text='')
                            self.images[name].photo = picture
                        else:
                            self.images[name].configure(image='', text='세 숫자 확인 중')
                            self.images[name].photo = None
                    key, text = advice(values, int(self.phase.get()), self.high, self.low)
                    self.message.set(text)
                    self.alert_key = key
                    self.refresh_alert()
                    self.status.set('모니터링 중 · 3회 연속 인식 확인 · 숫자가 안 읽히면 해당 값은 —로 표시')
                    if self.voice.get() and self.volume.get() > 0 and not self.speaker.busy and self.gate.allow(key, time.monotonic()):
                        self.speaker.speak(spoken_advice(key, text), self.volume.get())
        except queue.Empty:
            pass
        if not self.worker or not self.worker.is_alive():
            self.start_button.configure(state='normal')
        if self.speaker.error:
            self.status.set(self.speaker.error)
            self.speaker.error = None
        self.root.after(100, self.poll)

    def close(self):
        self.stop.set()
        self.settings_save()
        self.root.destroy()


if __name__ == '__main__':
    load_bundled_fonts()
    if len(sys.argv) == 3 and sys.argv[1] == '--check-voice':
        assets = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        for clip in ('red','green','yellow','limit','conflict'):
            Speaker.play_clip(assets / 'assets' / 'voice' / f'{clip}.wav', 0)
        Path(sys.argv[2]).write_text('Male voice: 5 clips decoded and played at volume 0', encoding='utf-8')
    elif len(sys.argv) == 4 and sys.argv[1] in ('--check-ocr', '--check-gauge'):
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        value = read_gauge(engine, Image.open(sys.argv[2]))[0] if sys.argv[1] == '--check-gauge' else read_digits(engine, Image.open(sys.argv[2]))
        Path(sys.argv[3]).write_text(json.dumps({'value': value, 'tkinter_import': True}), encoding='utf-8')
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()
