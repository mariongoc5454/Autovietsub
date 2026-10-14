import os
import re
import traceback
import time
import asyncio
import subprocess
from pydub import AudioSegment
import edge_tts

class TTSEngine:
    def __init__(self, ffmpeg_path, logger):
        self.ffmpeg_path = ffmpeg_path
        self.log = logger
        
    def generate_dubbing(self, segments, translated_texts, video_path, voice_id, update_progress_cb, stop_event=None, ref_audio_path=None, remove_vocals=False):
        try:
            # 1. VERIFY VOICE USING EDGE-TTS LIBRARY (VIETNAMESE-ONLY MODE)
            async def verify_voice():
                if voice_id == "ai-voice-clone":
                    return True # Bỏ qua kiểm tra Edge-TTS cho AI Clone
                    
                voices = await edge_tts.list_voices()
                for v in voices:
                    if v['ShortName'] == voice_id:
                        if v['Locale'] != 'vi-VN':
                            raise Exception(f"Voice '{voice_id}' có locale '{v['Locale']}', không phải 'vi-VN'. Vietnamese-only mode từ chối voice này.")
                        return True
                raise Exception(f"Voice '{voice_id}' không tồn tại trong hệ thống Edge-TTS!")
            
            asyncio.run(verify_voice())

            dub_audio_path = video_path.rsplit('.', 1)[0] + "_dub.wav"
            
            if remove_vocals:
                update_progress_cb("Đang tắt hoàn toàn âm thanh gốc của video...")
                original_audio = AudioSegment.from_file(video_path)
                # Giảm 100dB coi như tắt tiếng hoàn toàn (Mute)
                final_audio = original_audio - 100
            else:
                original_audio = AudioSegment.from_file(video_path)
                final_audio = original_audio - 15
                
            # --- VIE NEU TTS INIT ---
            ref_audio_path_to_use = ref_audio_path
            if voice_id == "ai-voice-clone":
                try:
                    from vieneu import Vieneu
                except ImportError:
                    raise Exception("Chưa cài thư viện 'vieneu'. Vui lòng chạy lệnh: pip install vieneu")
                
                if not hasattr(self, 'vieneu_tts'):
                    self.log("Đang khởi tạo mô hình VieNeu-TTS (chạy trên CPU, sẽ mất chút thời gian ở lần đầu)...")
                    # Dùng bản Turbo xịn nhất. Cấu hình máy bạn tốt nên mình mở khóa lại bản này.
                    self.vieneu_tts = Vieneu(mode="v3turbo", precision="int8")
                
                if not ref_audio_path_to_use:
                    import tempfile
                    ref_audio_path_to_use = os.path.join(tempfile.gettempdir(), "ref_vieneu_audio.wav")
                    if segments:
                        start_ms = int(segments[0].start * 1000)
                        end_ms = start_ms + 4000
                        ref_chunk = original_audio[start_ms:end_ms]
                    else:
                        ref_chunk = original_audio[:4000]
                    ref_chunk.export(ref_audio_path_to_use, format="wav")
            # ------------------------
            
            dub_pieces = []
            total_segs = len(segments)
            
            for i, seg in enumerate(segments):
                if stop_event and stop_event.is_set():
                    raise Exception("Tác vụ bị hủy bởi người dùng!")
                update_progress_cb(f"75% - Lồng tiếng câu {i+1}/{total_segs}...")
                
                raw_text = translated_texts[i]
                
                # Xóa an toàn các tag thời lượng do AI sinh ra (vd: (1.5s), [2.0], 1.5s ) mà không xóa số thật ở đầu câu
                clean_text = re.sub(r'^[\(\[]\s*\d+(?:[\.,]\d+)?\s*[sS]?\s*[\)\]]\s*', '', raw_text)
                clean_text = re.sub(r'^\d+(?:[\.,]\d+)?\s*[sS]\s+', '', clean_text)
                clean_text = re.sub(r'^\d+\s*(?:[\|\]\)\:]|\.(?=\s)|\-(?=\s))\s*', '', clean_text)
                
                clean_text = re.sub(r'[<>&*~#@^\[\](){}]', '', clean_text)
                clean_text = clean_text.replace('\n', ' ').replace('-', ' ').replace('"', '').replace("'", "").strip()
                clean_text = " ".join(clean_text.split())
                
                # Bắt Hán Tự (Chinese Characters) do AI hallucinate hoặc do script gốc rò rỉ
                if re.search(r'[\u4e00-\u9fff]', clean_text):
                    self.log(f"⚠️ Cảnh báo câu {i+1} có chứa chữ Hán: '{clean_text}'")
                    if not re.search(r'[a-zA-ZÀ-ỹ]', clean_text):
                        self.log(f"⚠️ Bỏ qua đọc câu {i+1} vì chứa toàn chữ Hán, không có chữ Việt/Alphabet.")
                        continue
                        
                if not re.search(r'[a-zA-ZÀ-ỹ0-9]', clean_text):
                    self.log(f"⚠️ Bỏ qua đọc câu {i+1} do không chứa chữ Tiếng Việt hợp lệ.")
                    continue
                
                import tempfile
                temp_raw = os.path.join(tempfile.gettempdir(), f"temp_raw_{i}.mp3")
                temp_speed = os.path.join(tempfile.gettempdir(), f"temp_speed_{i}.wav")
                
                tts_success = False
                last_error = ""
                
                for attempt in range(3):
                    try:
                        if voice_id == "ai-voice-clone":
                            # THUẬT TOÁN BỌC THÉP: Chia nhỏ câu dài để tránh ONNX Crash
                            def split_text(txt):
                                import re
                                if len(txt) < 80: return [txt]
                                parts = re.split(r'([.?!,;])', txt)
                                chunks, cur = [], ""
                                for p in parts:
                                    if re.match(r'[.?!,;]', p):
                                        cur += p
                                        if len(cur) > 40:
                                            chunks.append(cur.strip())
                                            cur = ""
                                    else:
                                        cur += p
                                if cur.strip(): chunks.append(cur.strip())
                                return chunks if chunks else [txt]
                            
                            chunks = split_text(clean_text)
                            combined_audio = None
                            for idx_chunk, chunk_txt in enumerate(chunks):
                                if not chunk_txt: continue
                                chunk_data = self.vieneu_tts.infer(text=chunk_txt, ref_audio=ref_audio_path_to_use)
                                chunk_tmp = temp_raw.replace(".mp3", f"_part{idx_chunk}.wav")
                                self.vieneu_tts.save(chunk_data, chunk_tmp)
                                
                                part_audio = AudioSegment.from_file(chunk_tmp)
                                if combined_audio is None:
                                    combined_audio = part_audio
                                else:
                                    combined_audio += part_audio
                                os.remove(chunk_tmp)
                                
                            if combined_audio:
                                combined_audio.export(temp_raw, format="wav")
                            tts_success = True
                            break
                        else:
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
            if str(e) == "Tác vụ bị hủy bởi người dùng!":
                self.log("🛑 Quá trình lồng tiếng đã được dừng an toàn theo yêu cầu của bạn.")
            else:
                self.log(f"⚠️ Lỗi lồng tiếng Audio: {e}\nChi tiết lỗi:\n{traceback.format_exc()}")
            return None