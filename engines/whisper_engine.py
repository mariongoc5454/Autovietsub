import os
import sys
import re

# 1. TẮT SYMLINK TRƯỚC
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

# 2. ÉP NẠP DLL VÀO HỆ THỐNG TRƯỚC KHI GỌI WHISPER
if sys.platform == "win32":
    # Hỗ trợ cả khi chạy từ mã nguồn hoặc bản build (PyInstaller)
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    cuda_bin = os.path.join(base_dir, "venv", "Lib", "site-packages", "nvidia", "cublas", "bin")
    cudnn_bin = os.path.join(base_dir, "venv", "Lib", "site-packages", "nvidia", "cudnn", "bin")
    
    # Nhét thẳng vào biến môi trường PATH của Windows (Cách mạnh nhất)
    for path in [cuda_bin, cudnn_bin]:
        if os.path.exists(path):
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(path)
            except Exception:
                pass

# 3. KHI ĐÃ CÓ ĐỦ DLL RỒI MỚI ĐƯỢC IMPORT WHISPER (QUAN TRỌNG)
from faster_whisper import WhisperModel

def smart_merge_segments(original_segments):
    merged_segments = []
    current_seg = None

    for seg in original_segments:
        if current_seg is None:
            current_seg = seg
        else:
            # Gộp nếu khoảng cách < 0.5s HOẶC câu trước chưa có dấu kết thúc
            gap = seg.start - current_seg.end
            if gap < 0.5 or not re.search(r'[.?!]$', current_seg.text.strip()):
                current_seg = type('Segment', (object,), {
                    'start': current_seg.start,
                    'end': seg.end,
                    'text': current_seg.text.strip() + " " + seg.text.strip()
                })()
            else:
                merged_segments.append(current_seg)
                current_seg = seg
                
    if current_seg:
        merged_segments.append(current_seg)
        
    return merged_segments

class WhisperEngine:
    _instance = None
    @classmethod
    def get_model(cls, model_name="large-v3-turbo"):
        if cls._instance is None:
            try:
                # Thử nạp với float16 (nhanh nhất, chất lượng tốt nhất)
                cls._instance = WhisperModel(model_name, device="cuda", compute_type="float16")
            except Exception as e:
                # Nếu thiếu VRAM, lùi xuống int8_float16 (tiết kiệm ~50% VRAM)
                try:
                    cls._instance = WhisperModel(model_name, device="cuda", compute_type="int8_float16")
                except Exception as e2:
                    # Nếu vẫn sập, chạy bằng CPU (chậm hơn nhưng bao không sập)
                    cls._instance = WhisperModel(model_name, device="cpu", compute_type="int8")
        return cls._instance