import os
import sys
import re

# 1. TẮT SYMLINK TRƯỚC
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

# 2. ÉP NẠP DLL VÀO HỆ THỐNG TRƯỚC KHI GỌI WHISPER
if sys.platform == "win32":
    cuda_bin = r"D:\AutoSub_V4\venv\Lib\site-packages\nvidia\cublas\bin"
    cudnn_bin = r"D:\AutoSub_V4\venv\Lib\site-packages\nvidia\cudnn\bin"
    
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
            # Ép dùng card đồ họa (cuda) + float16 để RTX 2050 chạy tối đa công suất
            cls._instance = WhisperModel(model_name, device="cuda", compute_type="float16")
        return cls._instance