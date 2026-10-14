import os
import sys
import time
import threading
import json
import subprocess

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageFilter, ImageDraw

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    class CustomTk(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
    HAS_DND = True
except ImportError:
    CustomTk = ctk.CTk
    HAS_DND = False

# --- BẮT ĐẦU VÁ LỖI SPAM CONSOLE ---
if os.name == 'nt':
    class PatchedPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            if 'creationflags' not in kwargs:
                kwargs['creationflags'] = 0x08000000
            else:
                kwargs['creationflags'] |= 0x08000000
            super().__init__(*args, **kwargs)
            
    subprocess.Popen = PatchedPopen
# --- KẾT THÚC VÁ LỖI ---

from core.cache_manager import CacheManager
from core.key_manager import KeyManager
from core.ai_dispatcher import AIDispatcher
from engines.whisper_engine import WhisperEngine
from engines.translator_engine import TranslatorEngine
from engines.tts_engine import TTSEngine
from engines.render_engine import RenderEngine
from engines.sub_detector_engine import SubDetectorEngine

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def get_base_path():
    if getattr(sys, 'frozen', False): return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()
FFMPEG_PATH = os.path.join(BASE_PATH, "ffmpeg.exe") if os.path.exists(os.path.join(BASE_PATH, "ffmpeg.exe")) else os.path.join(BASE_PATH, "_internal", "ffmpeg.exe")

STYLE_MAP = {
    "TikTok (Chữ to, Nổi bật)": "Fontname=Arial,PrimaryColour=&HFFFFFF,Bold=1,BorderStyle=1,Outline=2,Shadow=1",
    "Netflix (Bóng mờ, Sang)": "Fontname=Arial,PrimaryColour=&HFFFFFF,Bold=0,BorderStyle=1,Outline=0.5,Shadow=1.5",
    "Classic (Viền đen dày)": "Fontname=Arial,PrimaryColour=&HFFFFFF,Bold=1,BorderStyle=1,Outline=2.5,Shadow=0"
}

VOICE_MAP = {
    "👩 Nữ (Hoài My - Vui vẻ)": "vi-VN-HoaiMyNeural",
    "👨 Nam (Nam Minh - Vui vẻ)": "vi-VN-NamMinhNeural",
    "🎙️ AI Clone (Giữ giọng gốc)": "ai-voice-clone"
}

voices_dir = os.path.join(BASE_PATH, "voices")
if not os.path.exists(voices_dir):
    os.makedirs(voices_dir, exist_ok=True)
else:
    for f in os.listdir(voices_dir):
        if f.lower().endswith(('.wav', '.mp3', '.m4a')):
            name = os.path.splitext(f)[0]
            VOICE_MAP[f"🎙️ Clone: {name}"] = f"ai-clone:{f}"

class CustomVideoCard(ctk.CTkFrame):
    def __init__(self, master, filename, variable):
        super().__init__(master, fg_color="#2A2A2A", corner_radius=12)
        self.variable = variable
        self.filename = filename
        
        self.checkbox = ctk.CTkCheckBox(
            self, text="", variable=self.variable, width=24, checkbox_height=20, checkbox_width=20, 
            fg_color="#3B82F6", hover_color="#2563EB", border_color="#555555"
        )
        self.checkbox.pack(side="left", padx=(15, 5), pady=12)
        
        self.lbl_title = ctk.CTkLabel(self, text=self.filename, font=("Segoe UI", 13, "bold"), text_color="#E0E0E0")
        self.lbl_title.pack(side="left", padx=8, pady=12, fill="x", expand=True)
        
        self.lbl_status = ctk.CTkLabel(self, text="⚪ Waiting", font=("Segoe UI", 12, "bold"), text_color="#888888")
        self.lbl_status.pack(side="right", padx=15, pady=12)
        
        self.bind("<Enter>", self.on_hover)
        self.bind("<Leave>", self.on_leave)
        
    def on_hover(self, event):
        self.configure(fg_color="#323232")
        
    def on_leave(self, event):
        self.configure(fg_color="#2A2A2A")

    def configure(self, require_redraw=False, **kwargs):
        if "text_color" in kwargs:
            color = kwargs.pop("text_color")
            self.lbl_title.configure(text_color=color)
            if color == "#00FFFF":
                self.lbl_status.configure(text="🟡 Processing", text_color="#FACC15")
            elif color == "#00FF00":
                self.lbl_status.configure(text="🟢 Done", text_color="#22C55E")
            elif color == "#FF0000":
                self.lbl_status.configure(text="🔴 Error", text_color="#EF4444")
            else:
                self.lbl_status.configure(text_color=color)
        if kwargs:
            super().configure(require_redraw=require_redraw, **kwargs)

class AutoSub_Enterprise_UI:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoSub AI - Professional Subtitle Studio")
        self.root.geometry("1100x700")
        self.root.minsize(900, 650)
        self.root.configure(fg_color="#181818")
        
        self.video_paths = []
        self.checkbox_dict = {}
        self.processed_videos = set()
        self.current_processing_video = None
        
        self.stop_event = threading.Event()
        self.original_preview_img = None
        self.active_drag_item = None
        
        self.sub_enabled = ctk.BooleanVar(value=True)
        
        self.blur_enabled = ctk.BooleanVar(value=True)
        self.blur_height_var = ctk.IntVar(value=70)
        self.blur_strength_var = ctk.IntVar(value=18)
        self.blur_offset = 10
        
        self.logo_blur_enabled = ctk.BooleanVar(value=True)
        self.logo_size_var = ctk.IntVar(value=15)
        
        self.bg_music_enabled = ctk.BooleanVar(value=False)
        self.bg_music_path_var = ctk.StringVar(value="")
        self.bg_music_path = ""
        self.bg_music_volume_var = ctk.IntVar(value=20)
        
        self.subtitle_y_ratio = 0.85
        self.blur_y_ratio = self.subtitle_y_ratio + (self.blur_offset / 292)
        
        self.cache_mgr = CacheManager()
        self.key_mgr = KeyManager()
        self.dispatcher = AIDispatcher(self.key_mgr, self.update_log)
        self.translator = TranslatorEngine(self.dispatcher, self.cache_mgr, self.update_log)
        self.tts_engine = TTSEngine(FFMPEG_PATH, self.update_log)
        self.render_engine = RenderEngine(FFMPEG_PATH, self.update_log)
        self.sub_detector = None
        
        self.setup_ui()
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        
        self.create_header()
        
        main_container = ctk.CTkFrame(self.root, fg_color="transparent")
        main_container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 10))
        main_container.grid_columnconfigure(0, weight=4)
        main_container.grid_columnconfigure(1, weight=6)
        main_container.grid_rowconfigure(0, weight=1)

        left_col = ctk.CTkFrame(main_container, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_col.grid_rowconfigure(0, weight=1)

        right_col = ctk.CTkFrame(main_container, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        right_col.grid_rowconfigure(1, weight=1)

        self.create_queue_panel(left_col)
        self.create_settings_panel(left_col)
        
        self.create_preview_panel(right_col)
        self.create_progress_log_panel(right_col)
        self.create_render_panel(right_col)
        
        self.create_statusbar()
        self.font_var.trace_add("write", self.draw_blur_preview)

    def create_header(self):
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 16))
        
        ctk.CTkLabel(header, text="🚀 AutoSub AI", font=("Segoe UI", 28, "bold"), text_color="#FFFFFF").pack(side="left")
        
        badges = ctk.CTkFrame(header, fg_color="transparent")
        badges.pack(side="right")
        ctk.CTkLabel(badges, text="Professional Subtitle Studio", font=("Segoe UI", 13), text_color="#A0A0A0").pack(side="top", anchor="e")
        ctk.CTkLabel(badges, text="GPT • Gemini • DeepSeek", font=("Segoe UI", 11, "bold"), text_color="#3B82F6").pack(side="top", anchor="e")

    def create_queue_panel(self, parent):
        queue_frame = ctk.CTkFrame(parent, fg_color="#222222", corner_radius=14)
        queue_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        header_row = ctk.CTkFrame(queue_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(header_row, text="🎬 Video Queue", font=("Segoe UI", 16, "bold"), text_color="#FFFFFF").pack(side="left")
        
        self.btn_select = ctk.CTkButton(header_row, text="➕ Add Videos", command=self.add_videos, width=100, height=32, corner_radius=8, font=("Segoe UI", 12, "bold"), fg_color="#3B82F6", hover_color="#2563EB")
        self.btn_select.pack(side="right")
        
        self.btn_remove = ctk.CTkButton(header_row, text="🗑 Remove", command=self.remove_video, width=80, height=32, corner_radius=8, font=("Segoe UI", 12, "bold"), fg_color="#EF4444", hover_color="#DC2626")
        self.btn_remove.pack(side="right", padx=(0, 10))
        
        self.scroll_frame = ctk.CTkScrollableFrame(queue_frame, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 15))
        
        if HAS_DND:
            queue_frame.drop_target_register(DND_FILES)
            queue_frame.dnd_bind('<<Drop>>', self.on_drop)
            self.scroll_frame.drop_target_register(DND_FILES)
            self.scroll_frame.dnd_bind('<<Drop>>', self.on_drop)
            ctk.CTkLabel(queue_frame, text="⬇️ Kéo thả video vào đây", font=("Segoe UI", 12, "italic"), text_color="#666666").pack(side="bottom", pady=(0, 10))

    def create_settings_panel(self, parent):
        settings_frame = ctk.CTkFrame(parent, fg_color="transparent")
        settings_frame.grid(row=1, column=0, sticky="nsew")
        
        card1 = ctk.CTkFrame(settings_frame, fg_color="#222222", corner_radius=14)
        card1.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card1, text="🧠 AI Engine & Format", font=("Segoe UI", 14, "bold"), text_color="#FFFFFF").pack(anchor="w", padx=20, pady=(15, 5))
        
        row1 = ctk.CTkFrame(card1, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=(0, 15))
        
        self.model_var = ctk.StringVar(value="gpt-4o")
        self.combo_model = ctk.CTkComboBox(row1, values=["gpt-4o-mini", "gemini-3.5-flash-lite", "DeepSeek-V3-0324", "gpt-4o"], variable=self.model_var, command=self.save_config, corner_radius=10, fg_color="#181818", border_width=1, border_color="#323232")
        self.combo_model.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.format_var = ctk.StringVar(value="💻 Máy tính (Ngang - Dàn 1 dòng)")
        ctk.CTkComboBox(row1, values=["💻 Máy tính (Ngang - Dàn 1 dòng)", "📱 Điện thoại (Dọc - Ngắt 2 dòng)"], variable=self.format_var, corner_radius=10, fg_color="#181818", border_width=1, border_color="#323232").pack(side="left", fill="x", expand=True)
        
        card2 = ctk.CTkFrame(settings_frame, fg_color="#222222", corner_radius=14)
        card2.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card2, text="📝 Subtitle Appearance", font=("Segoe UI", 14, "bold"), text_color="#FFFFFF").pack(anchor="w", padx=20, pady=(15, 5))
        
        row2 = ctk.CTkFrame(card2, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=(0, 15))
        
        ctk.CTkSwitch(row2, text="☑ Render Vietsub", variable=self.sub_enabled, command=self.draw_blur_preview, font=("Segoe UI", 12), progress_color="#3B82F6").pack(side="left", padx=(0, 10))
        
        self.style_var = ctk.StringVar(value="TikTok (Chữ to, Nổi bật)")
        ctk.CTkComboBox(row2, values=list(STYLE_MAP.keys()), variable=self.style_var, corner_radius=10, fg_color="#181818", border_width=1, border_color="#323232").pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.font_var = ctk.StringVar(value="22")
        ctk.CTkComboBox(row2, values=["16", "20", "22", "26", "32"], variable=self.font_var, width=80, corner_radius=10, fg_color="#181818", border_width=1, border_color="#323232").pack(side="right")
        
        card3 = ctk.CTkFrame(settings_frame, fg_color="#222222", corner_radius=14)
        card3.pack(fill="x")
        ctk.CTkLabel(card3, text="🎙️ Voice & Rendering Options", font=("Segoe UI", 14, "bold"), text_color="#FFFFFF").pack(anchor="w", padx=20, pady=(15, 5))
        
        row3 = ctk.CTkFrame(card3, fg_color="transparent")
        row3.pack(fill="x", padx=20, pady=(0, 10))
        self.voice_var = ctk.StringVar(value="👩 Nữ (Hoài My - Vui vẻ)")
        self.combo_voice = ctk.CTkComboBox(row3, values=list(VOICE_MAP.keys()), variable=self.voice_var, corner_radius=10, fg_color="#181818", border_width=1, border_color="#323232")
        self.combo_voice.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.ref_audio_path = ""
        self.btn_select_ref = ctk.CTkButton(row3, text="🎵 Tự Chọn Giọng", command=self.select_ref_audio, width=120, fg_color="#4B5563", hover_color="#374151")
        self.btn_select_ref.pack(side="left", padx=(0, 15))
        
        self.dub_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(row3, text="AI Dub", variable=self.dub_var, font=("Segoe UI", 12), progress_color="#3B82F6").pack(side="left", padx=(0, 15))
        
        self.mute_original_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(row3, text="🔇 Tắt Tiếng Video Gốc", variable=self.mute_original_var, font=("Segoe UI", 12), progress_color="#EF4444").pack(side="left")

        row4 = ctk.CTkFrame(card3, fg_color="transparent")
        row4.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkSwitch(row4, text="🧹 Blur Original Subtitle", variable=self.blur_enabled, command=self.draw_blur_preview, font=("Segoe UI", 12), progress_color="#3B82F6").pack(side="left", padx=(0, 15))
        ctk.CTkLabel(row4, text="↕ Height:", font=("Segoe UI", 12), text_color="#A0A0A0").pack(side="left")
        ctk.CTkSlider(row4, from_=20, to=200, variable=self.blur_height_var, command=self.draw_blur_preview, width=90, progress_color="#FACC15").pack(side="left", padx=(5, 10))
        ctk.CTkLabel(row4, text="💧 Str:", font=("Segoe UI", 12), text_color="#A0A0A0").pack(side="left")
        ctk.CTkSlider(row4, from_=5, to=50, variable=self.blur_strength_var, command=self.draw_blur_preview, width=80, progress_color="#FACC15").pack(side="left", padx=(5, 0))

        row5 = ctk.CTkFrame(card3, fg_color="transparent")
        row5.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkSwitch(row5, text="⭕ Blur Logo Kỳ Lân", variable=self.logo_blur_enabled, command=self.draw_blur_preview, font=("Segoe UI", 12), progress_color="#3B82F6").pack(side="left", padx=(0, 15))
        ctk.CTkLabel(row5, text="📏 Size:", font=("Segoe UI", 12), text_color="#A0A0A0").pack(side="left")
        ctk.CTkSlider(row5, from_=5, to=40, variable=self.logo_size_var, command=self.draw_blur_preview, width=150, progress_color="#FACC15").pack(side="left", padx=(5, 0))

        row6 = ctk.CTkFrame(card3, fg_color="transparent")
        row6.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkSwitch(row6, text="🎵 Chèn Nhạc Nền", variable=self.bg_music_enabled, font=("Segoe UI", 12), progress_color="#3B82F6").pack(side="left", padx=(0, 15))
        self.btn_select_bg = ctk.CTkButton(row6, text="📂 Chọn Nhạc", command=self.select_bg_music, width=100, fg_color="#4B5563", hover_color="#374151")
        self.btn_select_bg.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(row6, text="🔊 Âm lượng:", font=("Segoe UI", 12), text_color="#A0A0A0").pack(side="left")
        ctk.CTkSlider(row6, from_=1, to=100, variable=self.bg_music_volume_var, width=120, progress_color="#FACC15").pack(side="left", padx=(5, 0))

    def select_bg_music(self):
        filepath = filedialog.askopenfilename(title="Chọn Nhạc Nền", filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.flac")])
        if filepath:
            self.bg_music_path = filepath
            self.bg_music_path_var.set(filepath)
            filename = os.path.basename(filepath)
            if len(filename) > 15:
                filename = filename[:12] + "..."
            self.btn_select_bg.configure(text=f"✅ {filename}", fg_color="#10B981", hover_color="#059669")
            self.bg_music_enabled.set(True)

    def select_ref_audio(self):
        filepath = filedialog.askopenfilename(title="Chọn file âm thanh mẫu (3-10s)", filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.flac")])
        if filepath:
            dialog = ctk.CTkInputDialog(text="Nhập tên để lưu lại giọng này (Để trống nếu chỉ dùng 1 lần):", title="Lưu giọng mẫu")
            name = dialog.get_input()
            if name:
                import shutil
                ext = os.path.splitext(filepath)[1]
                new_filename = f"{name}{ext}"
                new_path = os.path.join(BASE_PATH, "voices", new_filename)
                try:
                    shutil.copy(filepath, new_path)
                    self.ref_audio_path = new_path
                    self.btn_select_ref.configure(text=f"✅ {name}", fg_color="#10B981", hover_color="#059669")
                    
                    new_key = f"🎙️ Clone: {name}"
                    VOICE_MAP[new_key] = f"ai-clone:{new_filename}"
                    self.combo_voice.configure(values=list(VOICE_MAP.keys()))
                    self.voice_var.set(new_key)
                except Exception as e:
                    self.update_log(f"Lỗi khi lưu giọng: {e}")
            else:
                self.ref_audio_path = filepath
                self.btn_select_ref.configure(text="✅ Đã tải mẫu", fg_color="#10B981", hover_color="#059669")
                self.voice_var.set("🎙️ AI Clone (Giữ giọng gốc)")

    def create_preview_panel(self, parent):
        self.preview_frame = ctk.CTkFrame(parent, fg_color="#222222", corner_radius=14)
        self.preview_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        header_row = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header_row, text="📺 Subtitle Preview", font=("Segoe UI", 16, "bold"), text_color="#FFFFFF").pack(side="left")
        ctk.CTkLabel(header_row, text="(Drag objects below to position subtitles & blur)", font=("Segoe UI", 12), text_color="#888888").pack(side="left", padx=(10,0))
        
        self.canvas_width = 520
        self.canvas_height = 292
        self.preview_canvas = tk.Canvas(self.preview_frame, width=self.canvas_width, height=self.canvas_height, bg="#000000", highlightthickness=1, highlightbackground="#323232")
        self.preview_canvas.pack(pady=(5, 20))
        
        self.tk_img = None
        self.sub_position_var = ctk.DoubleVar(value=20) 
        
        self.preview_canvas.create_oval(0, 0, 0, 0, outline="#FACC15", width=2, dash=(4, 4), tag="logo_rect")
        self.preview_canvas.create_text(0, 0, text="Logo", fill="#FACC15", font=("Segoe UI", 10, "bold"), tag="logo_text")
        
        self.preview_canvas.create_rectangle(0, 0, self.canvas_width, self.blur_height_var.get(), outline="#FACC15", width=2, dash=(4, 4), tag="blur_rect")
        self.preview_canvas.create_text(self.canvas_width/2, 15, text="Blur Area", fill="#FACC15", font=("Segoe UI", 11, "bold"), tag="blur_text")
        
        self.preview_canvas.create_text(self.canvas_width/2, self.canvas_height - 40, text="[ Drag subtitle here ]", fill="#3B82F6", font=("Segoe UI", 18, "bold"), tag="subtitle", justify="center")
        
        self.preview_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)

    def create_progress_log_panel(self, parent):
        log_frame = ctk.CTkFrame(parent, fg_color="#222222", corner_radius=14)
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        
        prog_container = ctk.CTkFrame(log_frame, fg_color="transparent")
        prog_container.pack(fill="x", padx=20, pady=(20, 10))
        
        self.lbl_percent = ctk.CTkLabel(prog_container, text="0% - Waiting...", font=("Segoe UI", 13, "bold"), text_color="#3B82F6")
        self.lbl_percent.pack(anchor="w", pady=(0, 5))
        
        self.progress_bar = ctk.CTkProgressBar(prog_container, height=12, corner_radius=6, progress_color="#3B82F6", fg_color="#323232")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x")
        
        self.log_box = ctk.CTkTextbox(log_frame, fg_color="#181818", text_color="#A0A0A0", font=("Consolas", 13), corner_radius=12, border_width=1, border_color="#323232")
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.log_box.tag_config("timestamp", foreground="#6B7280")
        self.log_box.tag_config("error", foreground="#EF4444")
        self.log_box.tag_config("warning", foreground="#F59E0B")
        self.log_box.tag_config("success", foreground="#22C55E")
        self.log_box.tag_config("info", foreground="#E5E7EB")

    def create_render_panel(self, parent):
        btn_container = ctk.CTkFrame(parent, fg_color="transparent")
        btn_container.grid(row=2, column=0, sticky="nsew")
        btn_container.grid_columnconfigure(0, weight=7)
        btn_container.grid_columnconfigure(1, weight=3)
        
        self.btn_run = ctk.CTkButton(
            btn_container, text="🚀 START PROCESSING", command=self.start_process, 
            font=("Segoe UI", 18, "bold"), height=60, corner_radius=14, 
            fg_color="#3B82F6", hover_color="#2563EB", state="disabled"
        )
        self.btn_run.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        self.btn_cancel = ctk.CTkButton(
            btn_container, text="⏹ CANCEL", command=self.cancel_process, 
            font=("Segoe UI", 16, "bold"), height=60, corner_radius=14, 
            fg_color="#EF4444", hover_color="#DC2626", state="disabled"
        )
        self.btn_cancel.grid(row=0, column=1, sticky="nsew")

    def cancel_process(self):
        if self.current_processing_video:
            self.stop_event.set()
            self.btn_cancel.configure(state="disabled", text="Stopping...")
            self.update_log("🛑 Đang gửi tín hiệu hủy tác vụ, vui lòng đợi quá trình đồng bộ dừng lại...", 0)

    def create_statusbar(self):
        status_frame = ctk.CTkFrame(self.root, height=30, fg_color="#181818", corner_radius=0)
        status_frame.grid(row=2, column=0, sticky="ew")
        
        ctk.CTkLabel(status_frame, text="🟢 CUDA Ready", font=("Segoe UI", 11, "bold"), text_color="#22C55E").pack(side="left", padx=24)
        self.status_queue = ctk.CTkLabel(status_frame, text="Queue: 0", font=("Segoe UI", 11, "bold"), text_color="#888888")
        self.status_queue.pack(side="right", padx=24)

    def on_canvas_press(self, event):
        self._drag_y = event.y
        self.active_drag_item = None
        
        sub_coords = self.preview_canvas.coords("subtitle")
        if sub_coords:
            sub_y = sub_coords[1]
            if abs(event.y - sub_y) < 25:
                self.active_drag_item = "subtitle"
                return
                
        if self.blur_enabled.get():
            blur_coords = self.preview_canvas.coords("blur_rect")
            if blur_coords:
                if blur_coords[1] <= event.y <= blur_coords[3]:
                    self.active_drag_item = "blur_area"
                    return

    def on_canvas_drag(self, event):
        if not hasattr(self, 'active_drag_item') or not self.active_drag_item:
            return

        delta_y = event.y - self._drag_y
        
        if self.active_drag_item == "subtitle":
            coords = self.preview_canvas.coords("subtitle")
            new_y = coords[1] + delta_y
            if 15 < new_y < self.canvas_height - 15:
                self.preview_canvas.move("subtitle", 0, delta_y)
                self._drag_y = event.y
                self.subtitle_y_ratio = new_y / self.canvas_height
                
                margin_px = self.canvas_height - new_y
                self.sub_position_var.set(margin_px * (250 / self.canvas_height))
                
        elif self.active_drag_item == "blur_area":
            rect_coords = self.preview_canvas.coords("blur_rect")
            new_y_top = rect_coords[1] + delta_y
            current_blur_h = self.blur_height_var.get()
            
            if 0 <= new_y_top <= self.canvas_height - current_blur_h:
                self.preview_canvas.move("blur_rect", 0, delta_y)
                self.preview_canvas.move("blur_text", 0, delta_y)
                self._drag_y = event.y
                
                center_y = new_y_top + (current_blur_h / 2)
                self.blur_y_ratio = center_y / self.canvas_height
                
        self.draw_blur_preview()

    def draw_blur_preview(self, *args):
        try:
            f_size = int(self.font_var.get())
            display_size = int(f_size * 1.2) 
            self.preview_canvas.itemconfig("subtitle", font=("Segoe UI", display_size, "bold"))
            
            if hasattr(self, 'original_preview_img') and self.original_preview_img:
                draw_img = self.original_preview_img.copy()
                current_blur_h = self.blur_height_var.get()
                current_blur_strength = self.blur_strength_var.get()
                
                if self.blur_enabled.get():
                    img_height = draw_img.height
                    img_width = draw_img.width
                    
                    canvas_ratio = img_height / self.canvas_height
                    blur_h_actual = int(current_blur_h * canvas_ratio)
                    
                    start_y = int(img_height * self.blur_y_ratio) - int(blur_h_actual / 2)
                    start_y = max(0, min(start_y, img_height - blur_h_actual))
                    
                    crop_area = (0, start_y, img_width, start_y + blur_h_actual)
                    
                    cropped = draw_img.crop(crop_area)
                    cropped = cropped.filter(ImageFilter.GaussianBlur(radius=current_blur_strength / 2))
                    
                    overlay = Image.new('RGBA', cropped.size, (250, 204, 21, 50))
                    cropped = Image.alpha_composite(cropped.convert('RGBA'), overlay).convert('RGB')
                    
                    draw_img.paste(cropped, crop_area)
                
                if self.logo_blur_enabled.get():
                    percent = self.logo_size_var.get() / 100.0
                    size_px = int(draw_img.height * percent)
                    pos_px = int(draw_img.height * 0.03)
                    
                    box = (pos_px, pos_px, pos_px + size_px, pos_px + size_px)
                    
                    if box[2] <= draw_img.width and box[3] <= draw_img.height:
                        logo_crop = draw_img.crop(box)
                        logo_blurred = logo_crop.filter(ImageFilter.GaussianBlur(radius=10))
                        
                        mask = Image.new('L', (size_px, size_px), 0)
                        ImageDraw.Draw(mask).ellipse((0, 0, size_px, size_px), fill=255)
                        
                        overlay = Image.new('RGBA', (size_px, size_px), (250, 204, 21, 50))
                        logo_blended = Image.alpha_composite(logo_blurred.convert('RGBA'), overlay).convert('RGB')
                        
                        draw_img.paste(logo_blended, box, mask)
                    
                self.tk_img = ImageTk.PhotoImage(draw_img)
                self.preview_canvas.delete("bg_img")
                self.preview_canvas.create_image(self.canvas_width/2, self.canvas_height/2, image=self.tk_img, tag="bg_img")
                self.preview_canvas.tag_lower("bg_img")
                
                if self.blur_enabled.get():
                    self.preview_canvas.itemconfig("blur_rect", state="normal")
                    self.preview_canvas.itemconfig("blur_text", state="normal")
                    
                    center_y = self.blur_y_ratio * self.canvas_height
                    top_y = center_y - (current_blur_h / 2)
                    bottom_y = center_y + (current_blur_h / 2)
                    
                    self.preview_canvas.coords("blur_rect", 0, top_y, self.canvas_width, bottom_y)
                    self.preview_canvas.coords("blur_text", self.canvas_width/2, top_y + 15)
                else:
                    self.preview_canvas.itemconfig("blur_rect", state="hidden")
                    self.preview_canvas.itemconfig("blur_text", state="hidden")
                    
                if self.logo_blur_enabled.get():
                    self.preview_canvas.itemconfig("logo_rect", state="normal")
                    self.preview_canvas.itemconfig("logo_text", state="normal")
                    
                    pad_x = (self.canvas_width - draw_img.width) / 2
                    pad_y = (self.canvas_height - draw_img.height) / 2
                    
                    x1 = pad_x + pos_px
                    y1 = pad_y + pos_px
                    x2 = x1 + size_px
                    y2 = y1 + size_px
                    
                    self.preview_canvas.coords("logo_rect", x1, y1, x2, y2)
                    self.preview_canvas.coords("logo_text", x1 + size_px/2, y1 + size_px/2)
                else:
                    self.preview_canvas.itemconfig("logo_rect", state="hidden")
                    self.preview_canvas.itemconfig("logo_text", state="hidden")
                    
                # Ẩn/Hiện dòng chữ Vietsub Preview dựa theo công tắc
                if self.sub_enabled.get():
                    self.preview_canvas.itemconfig("subtitle", state="normal")
                else:
                    self.preview_canvas.itemconfig("subtitle", state="hidden")
        except Exception:
            pass

    def load_preview(self, video_path):
        import uuid
        def fetch_image():
            temp_img = f"temp_preview_{uuid.uuid4().hex}.jpg"
            try:
                cmd = [FFMPEG_PATH, "-y", "-i", video_path, "-ss", "00:00:02", "-vframes", "1", "-vf", f"scale={self.canvas_width}:{self.canvas_height}:force_original_aspect_ratio=decrease", temp_img]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                
                if os.path.exists(temp_img):
                    self.root.after(0, render_image, temp_img)
            except Exception as e:
                self.update_log(f"⚠️ Lỗi Preview: {e}")
                if os.path.exists(temp_img):
                    try:
                        os.remove(temp_img)
                    except Exception:
                        pass

        def render_image(img_path):
            try:
                original_img = Image.open(img_path)
                self.original_preview_img = original_img.copy()
                original_img.close()
                
                self.draw_blur_preview()
            except Exception:
                pass
            finally:
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass

        threading.Thread(target=fetch_image, daemon=True).start()

    def load_config(self):
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "model" in data: self.model_var.set(data["model"])
                    if "format" in data: self.format_var.set(data["format"])
                    if "style" in data: self.style_var.set(data["style"])
                    if "font" in data: self.font_var.set(data["font"])
                    if "voice" in data: self.voice_var.set(data["voice"])
                    if "sub_enabled" in data: self.sub_enabled.set(data["sub_enabled"])
                    if "dub_enabled" in data: self.dub_var.set(data["dub_enabled"])
                    if "blur_enabled" in data: self.blur_enabled.set(data["blur_enabled"])
                    if "blur_height" in data: self.blur_height_var.set(data["blur_height"])
                    if "blur_strength" in data: self.blur_strength_var.set(data["blur_strength"])
                    if "logo_blur_enabled" in data: self.logo_blur_enabled.set(data["logo_blur_enabled"])
                    if "logo_size" in data: self.logo_size_var.set(data["logo_size"])
                    if "sub_position" in data: self.sub_position_var.set(data["sub_position"])
                    if "bg_music_enabled" in data: self.bg_music_enabled.set(data["bg_music_enabled"])
                    if "bg_music_path" in data:
                        path = data["bg_music_path"]
                        if path and os.path.exists(path):
                            self.bg_music_path = path
                            self.bg_music_path_var.set(path)
                            filename = os.path.basename(path)
                            if len(filename) > 15: filename = filename[:12] + "..."
                            if hasattr(self, 'btn_select_bg'):
                                self.btn_select_bg.configure(text=f"✅ {filename}", fg_color="#10B981", hover_color="#059669")
                    if "bg_music_volume" in data: self.bg_music_volume_var.set(data["bg_music_volume"])
        except Exception: pass

    def save_config(self, *args):
        try:
            data = {
                "model": self.model_var.get(),
                "format": self.format_var.get(),
                "style": self.style_var.get(),
                "font": self.font_var.get(),
                "voice": self.voice_var.get(),
                "sub_enabled": self.sub_enabled.get(),
                "dub_enabled": self.dub_var.get(),
                "blur_enabled": self.blur_enabled.get(),
                "blur_height": self.blur_height_var.get(),
                "blur_strength": self.blur_strength_var.get(),
                "logo_blur_enabled": self.logo_blur_enabled.get(),
                "logo_size": self.logo_size_var.get(),
                "sub_position": self.sub_position_var.get(),
                "bg_music_enabled": self.bg_music_enabled.get(),
                "bg_music_path": self.bg_music_path,
                "bg_music_volume": self.bg_music_volume_var.get()
            }
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception: pass

    def on_closing(self):
        self.save_config()
        self.root.destroy()

    def update_log(self, msg, percent=None): 
        self.root.after(0, self._update_ui, msg, percent)

    def _update_ui(self, msg, percent):
        if percent is not None:
            self.progress_bar.set(percent / 100)
            self.lbl_percent.configure(text=str(percent) if "%" in str(percent) else f"{percent}%")
            
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ", "timestamp")
        
        if "LỖI" in msg.upper() or "❌" in msg:
            self.log_box.insert(tk.END, f"{msg}\n", "error")
        elif "⚠️" in msg:
            self.log_box.insert(tk.END, f"{msg}\n", "warning")
        elif "✓" in msg or "🎉" in msg or "HOÀN TẤT" in msg:
            self.log_box.insert(tk.END, f"{msg}\n", "success")
        else:
            self.log_box.insert(tk.END, f"{msg}\n", "info")
            
        self.log_box.see(tk.END)

    def update_status_queue(self):
        if hasattr(self, 'status_queue'):
            chua_xu_ly = len(self.video_paths) - len(self.processed_videos)
            self.status_queue.configure(text=f"Queue: {chua_xu_ly}")

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        valid_exts = ['.mp4', '.mkv', '.mov', '.avi']
        paths = [f for f in files if any(f.lower().endswith(ext) for ext in valid_exts)]
        self._add_files_to_queue(paths)

    def add_videos(self):
        paths = filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.mkv *.mov *.avi")])
        if paths:
            self._add_files_to_queue(paths)

    def _add_files_to_queue(self, paths):
        if not paths: return
        was_empty = len(self.video_paths) == 0
        added_any = False
        for p in paths:
            if p not in self.video_paths:
                self.video_paths.append(p)
                
                cb_var = ctk.IntVar()
                cb = CustomVideoCard(self.scroll_frame, filename=os.path.basename(p), variable=cb_var)
                cb.pack(fill="x", pady=5)
                self.checkbox_dict[p] = (cb, cb_var)
                added_any = True
                
        chua_xu_ly = len(self.video_paths) - len(self.processed_videos)
        if not self.current_processing_video and chua_xu_ly > 0:
            self.btn_run.configure(state="normal")
            
        self.update_log(f"📁 Đã thêm. Hàng đợi hiện có: {chua_xu_ly} video chờ.", 0)
        self.update_status_queue()

        if was_empty and added_any:
            self.load_preview(self.video_paths[0])

    def remove_video(self):
        paths_to_remove = []
        for p, (cb, cb_var) in self.checkbox_dict.items():
            if cb_var.get() == 1:
                if p == self.current_processing_video:
                    self.update_log(f"⚠️ Video '{os.path.basename(p)}' đang chạy, không thể xóa!")
                    cb_var.set(0)
                else:
                    paths_to_remove.append(p)
                
        if not paths_to_remove:
            return
            
        for p in paths_to_remove:
            if p in self.video_paths:
                self.video_paths.remove(p)
            if p in self.processed_videos:
                self.processed_videos.remove(p)
            cb, _ = self.checkbox_dict.pop(p)
            cb.destroy() 
            
        self.update_log(f"🗑️ Đã xóa {len(paths_to_remove)} video khỏi hàng đợi.", 0)
        self.update_status_queue()
        
        if len(self.video_paths) == 0 and not self.current_processing_video:
            self.btn_run.configure(state="disabled")

    def start_process(self):
        self.update_log("🚀 Đang khởi động hàng đợi xử lý...", 0)
        self.btn_run.configure(state="disabled")
        threading.Thread(target=self.run_pipeline, daemon=True).start()

    def run_pipeline(self):
        success_count = 0
        self.stop_event.clear()
        self.root.after(0, lambda: self.btn_cancel.configure(state="normal", text="⏹ CANCEL"))
        
        while not self.stop_event.is_set():
            next_video = None
            for p in self.video_paths:
                if p not in self.processed_videos:
                    next_video = p
                    break
                    
            if not next_video:
                break 
                
            self.current_processing_video = next_video
            
            try:
                self.update_log(f"\n--- BẮT ĐẦU XỬ LÝ VIDEO ---", 0)
                self.update_log(f"🎬 File: {os.path.basename(next_video)}")
                
                if next_video in self.checkbox_dict:
                    cb, _ = self.checkbox_dict[next_video]
                    self.root.after(0, lambda c=cb: c.configure(text_color="#00FFFF"))

                self.process_single_video(next_video)
                success_count += 1
                
                if next_video in self.checkbox_dict:
                    self.root.after(0, lambda c=cb: c.configure(text_color="#00FF00"))
                
            except Exception as e:
                if "Tác vụ bị hủy" in str(e):
                    self.update_log("🛑 TÁC VỤ ĐÃ BỊ HỦY BỞI NGƯỜI DÙNG.", 0)
                    if next_video in self.checkbox_dict:
                        self.root.after(0, lambda c=cb: c.configure(text_color="#888888"))
                        cb.lbl_status.configure(text="⚪ Cancelled")
                    self.processed_videos.add(next_video)
                    self.current_processing_video = None
                    break
                else:
                    self.update_log(f"❌ LỖI TẠI VIDEO NÀY: {str(e)}", 0)
                    self.update_log("⏭️ Bỏ qua và tự động chuyển sang video tiếp theo...", 0)
                    if next_video in self.checkbox_dict:
                        self.root.after(0, lambda c=cb: c.configure(text_color="#FF0000"))
                    
            finally:
                self.processed_videos.add(next_video)
                self.current_processing_video = None
                self.root.after(0, self.update_status_queue)

        if self.stop_event.is_set():
            self.update_log(f"\n⏹ Đã dừng toàn bộ hàng đợi.", 0)
        else:
            self.update_log(f"\n🎉 HOÀN TẤT! Đã xử lý thành công: {success_count} video.", 100)
        
        chua_xu_ly = len(self.video_paths) - len(self.processed_videos)
        self.root.after(0, lambda: self.btn_run.configure(state="normal" if chua_xu_ly > 0 else "disabled"))
        self.root.after(0, lambda: self.btn_cancel.configure(state="disabled", text="⏹ CANCEL"))

    def process_single_video(self, video_path):
        self.dispatcher.total_tokens_used = 0
        
        self.update_log(f"Đang nạp mô hình AI (có thể mất 1-2 phút lần đầu tải Whisper)...", 10)
        model = WhisperEngine.get_model()
        if self.stop_event.is_set(): raise Exception("Tác vụ bị hủy bởi người dùng!")
        
        segments, _ = model.transcribe(video_path, beam_size=5, vad_filter=True)
        seg_list = []
        for seg in segments:
            if self.stop_event.is_set(): raise Exception("Tác vụ bị hủy bởi người dùng!")
            seg_list.append(seg)
            
        total_segs = len(seg_list)
        if total_segs == 0: 
            raise Exception("Không tìm thấy âm thanh trong video này!")

        batches, current_batch = [], []
        for idx, seg in enumerate(seg_list):
            current_batch.append(seg)
            gap = (seg_list[idx+1].start - seg.end > 1.5) if idx < total_segs - 1 else False
            if len(current_batch) >= 8 or seg.text.strip().endswith(('.', '?', '!')) or gap:
                batches.append(current_batch)
                current_batch = []
        if current_batch: batches.append(current_batch)

        translated_texts = []
        for idx, batch in enumerate(batches):
            if self.stop_event.is_set(): raise Exception("Tác vụ bị hủy bởi người dùng!")
            self.update_log(f"Đang dịch Cụm {idx+1}/{len(batches)} (~{self.dispatcher.total_tokens_used} tokens)...", int(20 + (idx/len(batches))*40))
            s_idx = max(0, seg_list.index(batch[0]) - 10)
            e_idx = min(total_segs, seg_list.index(batch[-1]) + 5)
            ctx_str = " ".join([s.text for s in seg_list[s_idx:e_idx]])
            
            results = self.translator.process_smart_batch(batch, ctx_str, self.model_var.get(), self.stop_event)
            translated_texts.extend(results)

        dub_audio_path = None
        if self.dub_var.get():
            vid_voice = VOICE_MAP.get(self.voice_var.get())
            ref_audio = self.ref_audio_path if self.ref_audio_path else None
            
            if vid_voice and vid_voice.startswith("ai-clone:"):
                filename = vid_voice.split(":", 1)[1]
                ref_audio = os.path.join(BASE_PATH, "voices", filename)
                vid_voice = "ai-voice-clone"
                
            dub_audio_path = self.tts_engine.generate_dubbing(seg_list, translated_texts, video_path, vid_voice, lambda m: self.update_log(m), self.stop_event, ref_audio, remove_vocals=self.mute_original_var.get())

        self.update_log("Đang ghép phụ đề & Render Video...", 85)
        srt_path = video_path.rsplit('.', 1)[0] + ".srt"
        is_mobile = "Điện thoại" in self.format_var.get()
        
        self.render_engine.build_srt(seg_list, translated_texts, srt_path, is_mobile)
        if self.stop_event.is_set(): raise Exception("Tác vụ bị hủy bởi người dùng!")
        
        f_size = self.font_var.get()
        margin_v = str(int(self.sub_position_var.get()))
        f_style = f"Fontname=Arial,Fontsize={f_size},MarginV={margin_v}," + STYLE_MAP[self.style_var.get()].split("Fontname=Arial,")[1]
        
        blur_height_ratio = self.blur_height_var.get() / self.canvas_height
        final_blur_y = self.blur_y_ratio
        final_blur_h = blur_height_ratio
        
        if self.blur_enabled.get():
            self.update_log("🔍 Đang dùng AI dò tìm tự động vùng phụ đề cũ...", 90)
            if self.sub_detector is None:
                self.sub_detector = SubDetectorEngine(self.update_log)
            
            ai_blur_y, ai_blur_h = self.sub_detector.detect_subtitle_region(video_path)
            if ai_blur_y is not None and ai_blur_h is not None:
                final_blur_y = ai_blur_y
                final_blur_h = ai_blur_h
                self.update_log(f"✅ AI đã tìm thấy vùng chữ ở (Y: {final_blur_y:.2f}, Height: {final_blur_h:.2f})")
            else:
                self.update_log("⚠️ AI không tìm thấy phụ đề, sử dụng cài đặt thủ công.")
        
        out_vid = self.render_engine.render_video(
            video_path, srt_path, dub_audio_path, is_mobile, 
            self.blur_enabled.get(), f_style, 
            final_blur_y, self.blur_strength_var.get(), final_blur_h,
            self.logo_blur_enabled.get(), self.logo_size_var.get(),
            self.sub_enabled.get(), 
            self.bg_music_enabled.get(), self.bg_music_path, self.bg_music_volume_var.get(),
            self.stop_event
        )
        
        self.update_log(f"✓ Video xuất thành công: {os.path.basename(out_vid)}", 95)
        if dub_audio_path and os.path.exists(dub_audio_path): os.remove(dub_audio_path)

if __name__ == "__main__":
    try:
        import multiprocessing
        multiprocessing.freeze_support()
        root = CustomTk()
        app = AutoSub_Enterprise_UI(root)
        root.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("\n[CẢNH BÁO] Phần mềm bị văng! Cậu hãy copy lỗi ở trên rồi nhấn Enter để thoát...")