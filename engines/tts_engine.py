import os
import re
import time
import asyncio
import subprocess
from pydub import AudioSegment
import edge_tts

class TTSEngine:
    def __init__(self, ffmpeg_path, logger):
        self.ffmpeg_path = ffmpeg_path
        self.log = logger
        
    def generate_dubbing(self, segments, translated_texts, video_path, voice_id, update_progress_cb):
        try:
            dub_audio_path = video_path.rsplit('.', 1)[0] + "_dub.wav"
            original_audio = AudioSegment.from_file(video_path)
            final_audio = original_audio - 15 
            
            dub_pieces = []
            total_segs = len(segments)
            
            for i, seg in enumerate(segments):
                update_progress_cb(f"75% - Lồng tiếng câu {i+1}/{total_segs}...")
                
                raw_text = translated_texts[i]
                
                clean_text = re.sub(r'^[\(\[]?\d+(\.\d+)?[sS]?[\)\]]?\s*', '', raw_text)
                clean_text = re.sub(r'[<>&*~#@^\[\](){}]', '', clean_text)
                clean_text = clean_text.replace('\n', ' ').replace('-', ' ').replace('"', '').replace("'", "").strip()
                clean_text = " ".join(clean_text.split())
                
                if not re.search(r'[a-zA-ZÀ-ỹ0-9]', clean_text):
                    self.log(f"⚠️ Bỏ qua đọc câu {i+1} do không chứa chữ Tiếng Việt hợp lệ.")
                    continue
                
                temp_raw = f"temp_raw_{i}.mp3"
                temp_speed = f"temp_speed_{i}.wav"
                
                tts_success = False
                last_error = ""
                
                for attempt in range(3):
                    try:
                        async def run_tts():
                            comm = edge_tts.Communicate(clean_text, voice_id)
                            await comm.save(temp_raw)
                            return True
                        if asyncio.run(asyncio.wait_for(run_tts(), timeout=15.0)):
                            tts_success = True; break
                    except Exception as e:
                        last_error = str(e)
                        time.sleep(1)
                        
                if not tts_success:
                    self.log(f"⚠️ Lỗi TTS câu {i+1}: {last_error}")
                    continue
                    
                if os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 0:
                    seg_audio = AudioSegment.from_file(temp_raw)
                    audio_dur = len(seg_audio) / 1000.0
                    
                    # 1. Tính toán thời gian cần thiết (target_dur) từ khoảng thời gian của câu
                    target_dur = max(seg.end - seg.start, 0.1)
                    
                    # 2. Lấy khoảng trống an toàn đến câu tiếp theo (available_time)
                    if i < total_segs - 1:
                        next_start = segments[i+1].start
                        available_time = max(next_start - seg.start, 0.1)
                    else:
                        available_time = target_dur
                        
                    max_speed = 1.4
                    
                    # 3. Tăng tốc độ nếu cần thiết
                    if audio_dur > available_time:
                        ratio = audio_dur / available_time
                        final_ratio = min(ratio, max_speed)
                        
                        atempo = f"atempo={final_ratio}"
                        
                        # --- ĐÃ SỬA LỖI SPAM CỬA SỔ CMD Ở ĐÂY ---
                        subprocess.run([self.ffmpeg_path, "-y", "-i", temp_raw, "-filter:a", atempo, temp_speed], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                        
                        if os.path.exists(temp_speed) and os.path.getsize(temp_speed) > 0:
                            seg_audio = AudioSegment.from_file(temp_speed)
                            os.remove(temp_speed)
                            
                    dub_pieces.append((int(seg.start * 1000), seg_audio))
                    
                if os.path.exists(temp_raw): os.remove(temp_raw)
                    
            self.log("✓ Đang hòa âm trộn giọng (Mix Audio)...")
            if dub_pieces:
                dub_pieces.sort(key=lambda x: x[0])
                dub_track = AudioSegment.silent(duration=0)
                
                for start_ms, seg_audio in dub_pieces:
                    required_len = start_ms + len(seg_audio)
                    
                    if len(dub_track) < required_len:
                        padding_duration = required_len - len(dub_track)
                        dub_track += AudioSegment.silent(duration=padding_duration)
                        
                    dub_track = dub_track.overlay(seg_audio, position=start_ms)
                
                if len(final_audio) < len(dub_track):
                    final_audio += AudioSegment.silent(duration=(len(dub_track) - len(final_audio)))
                    
                final_audio = final_audio.overlay(dub_track)
                    
            final_audio.export(dub_audio_path, format="wav")
            return dub_audio_path
        except Exception as e:
            self.log(f"⚠️ Hủy lồng tiếng do trục trặc Audio: {e}")
            return Nonef