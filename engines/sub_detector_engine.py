import cv2
import numpy as np
from paddleocr import PaddleOCR
import subprocess
import tempfile
import os
import time

class SubDetectorEngine:
    def __init__(self, log_callback=None):
        self.log = log_callback if log_callback else print
        self.log("Đang khởi tạo AI Model (PaddleOCR)... Lần đầu có thể mất thêm vài giây.")
        # use_angle_cls=False, rec=False -> faster text detection only
        self.ocr = PaddleOCR(use_angle_cls=False, lang='ch', show_log=False)

    def extract_sample_frames(self, video_path, num_samples=3):
        temp_dir = tempfile.gettempdir()
        frames = []
        
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffprobe_exe = os.path.join(base_path, "ffprobe.exe")
        ffmpeg_exe = os.path.join(base_path, "ffmpeg.exe")
        
        cmd = f'"{ffprobe_exe}" -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{video_path}"'
        try:
            duration = float(subprocess.check_output(cmd, shell=True).decode('utf-8').strip())
        except:
            duration = 30
            
        timestamps = [duration * 0.3, duration * 0.5, duration * 0.7]
        
        for i, ts in enumerate(timestamps):
            out_path = os.path.join(temp_dir, f'sample_frame_{i}_{int(time.time())}.jpg')
            ff_cmd = f'"{ffmpeg_exe}" -y -ss {ts} -i "{video_path}" -vframes 1 -q:v 2 "{out_path}" -loglevel error'
            subprocess.run(ff_cmd, shell=True)
            if os.path.exists(out_path):
                frames.append(out_path)
                
        return frames

    def detect_subtitle_region(self, video_path):
        frames = self.extract_sample_frames(video_path)
        if not frames:
            return None, None
            
        y_mins = []
        y_maxs = []
        video_height = 0
        
        for frame_path in frames:
            img = cv2.imread(frame_path)
            if img is None: continue
            video_height, video_width, _ = img.shape
            
            result = self.ocr.ocr(img, cls=False, rec=True)
            
            if result is None or len(result) == 0 or result[0] is None or len(result[0]) == 0:
                continue
                
            boxes = result[0]
            
            frame_boxes = []
            for item in boxes:
                box_coords = item[0]
                y_coords = [point[1] for point in box_coords]
                frame_boxes.append((min(y_coords), max(y_coords)))
                
            if not frame_boxes: continue
            
            # Tìm dòng chữ thấp nhất ở đáy video
            lowest_max_y = max([b[1] for b in frame_boxes])
            
            # Phụ đề thường nằm ở 20% dưới cùng. Nếu dòng thấp nhất nằm cao hơn, bỏ qua.
            if lowest_max_y < video_height * 0.80:
                continue
                
            # Chỉ lấy các dòng chữ thuộc cụm phụ đề (nằm trong biên độ 15% chiều cao kể từ dòng đáy)
            for b_min, b_max in frame_boxes:
                if b_max > lowest_max_y - (video_height * 0.15):
                    y_mins.append(b_min)
                    y_maxs.append(b_max)
                    
            try:
                os.remove(frame_path)
            except:
                pass
            
        if not y_mins:
            return None, None
            
        final_y_min = min(y_mins)
        final_y_max = max(y_maxs)
        
        blur_height = final_y_max - final_y_min
        center_y = final_y_min + (blur_height / 2)
        
        padding = 15
        blur_height_ratio = (blur_height + padding * 2) / video_height
        blur_y_ratio = center_y / video_height
        
        return blur_y_ratio, blur_height_ratio
