import os
import ffmpeg
import pysrt
import subprocess
from engines.blur_engine import BlurEngine

class RenderEngine:
    def __init__(self, ffmpeg_path, logger):
        self.ffmpeg_path = ffmpeg_path
        self.log = logger
        
    def build_srt(self, segments, translated_texts, srt_path, is_mobile):
        subs = pysrt.SubRipFile()
        for i, (seg, trans) in enumerate(zip(segments, translated_texts)):
            MAX_CHARS, WRAP_LIMIT = (36, 18) if is_mobile else (75, 75)
            words = trans.split()
            chunks, cur_chunk, cur_len = [], [], 0
            for w in words:
                if cur_len + len(w) + 1 > MAX_CHARS and cur_chunk:
                    chunks.append(" ".join(cur_chunk))
                    cur_chunk, cur_len = [w], len(w)
                else:
                    cur_chunk.append(w); cur_len += len(w) + 1
            if cur_chunk: chunks.append(" ".join(cur_chunk))
            if not chunks: chunks = [trans]
            
            t_per_chunk = (seg.end - seg.start) / len(chunks)
            for c_idx, chunk in enumerate(chunks):
                c_start = seg.start + c_idx * t_per_chunk
                c_end = c_start + t_per_chunk
                f_chunk = chunk
                if len(chunk) > WRAP_LIMIT:
                    mid = len(chunk) // 2
                    s_idx = chunk.find(" ", mid)
                    if s_idx == -1: s_idx = chunk.rfind(" ", 0, mid)
                    if s_idx != -1: f_chunk = chunk[:s_idx] + "\n" + chunk[s_idx+1:]
                subs.append(pysrt.SubRipItem(len(subs)+1, start=pysrt.SubRipTime(seconds=c_start), end=pysrt.SubRipTime(seconds=c_end), text=f_chunk))
        subs.save(srt_path, encoding='utf-8')

    def render_video(self, video_path, srt_path, dub_audio_path, is_mobile, blur_enabled, final_style, blur_y_ratio, blur_strength, blur_height, logo_blur_enabled, logo_size_percent, sub_enabled):
        output_video = video_path.rsplit('.', 1)[0] + "_Vietsub.mp4"
        srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')
        
        # Dùng bộ lọc null nối thẳng luồng nếu tính năng Vietsub bị tắt
        if sub_enabled:
            vf_filter = f"subtitles='{srt_escaped}':force_style='{final_style}'"
        else:
            vf_filter = "null"
        
        # Gọi module Blur từ file blur_engine.py
        vf_filter = BlurEngine.apply_blur(vf_filter, blur_enabled, blur_y_ratio, blur_strength, blur_height, logo_blur_enabled, logo_size_percent)
        
        try:
            in_vid = ffmpeg.input(video_path)
            out_args = {"vcodec": "h264_nvenc", "preset": "fast"}
            
            if dub_audio_path and os.path.exists(dub_audio_path):
                in_aud = ffmpeg.input(dub_audio_path)
                out_args["acodec"] = "aac"
                stream = ffmpeg.output(in_vid.video, in_aud.audio, output_video, vf=vf_filter, **out_args)
            else:
                out_args["acodec"] = "copy"
                stream = ffmpeg.output(in_vid, output_video, vf=vf_filter, **out_args)
            
            cmd_args = ffmpeg.compile(stream.overwrite_output(), cmd=self.ffmpeg_path)
            result = subprocess.run(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Lỗi GPU Render: {error_msg}")
                
        except Exception as e:
            self.log("⚠️ Chuyển đổi sang CPU UltraFast...")
            out_args_cpu = {"vcodec": "libx264", "preset": "ultrafast", "threads": os.cpu_count()}
            
            in_vid = ffmpeg.input(video_path)
            if dub_audio_path and os.path.exists(dub_audio_path):
                in_aud = ffmpeg.input(dub_audio_path)
                out_args_cpu["acodec"] = "aac"
                stream = ffmpeg.output(in_vid.video, in_aud.audio, output_video, vf=vf_filter, **out_args_cpu)
            else:
                out_args_cpu["acodec"] = "copy"
                stream = ffmpeg.output(in_vid, output_video, vf=vf_filter, **out_args_cpu)
                
            cmd_args_cpu = ffmpeg.compile(stream.overwrite_output(), cmd=self.ffmpeg_path)
            
            result_cpu = subprocess.run(cmd_args_cpu, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result_cpu.returncode != 0:
                error_msg = result_cpu.stderr.decode('utf-8', errors='ignore')
                raise Exception(f"Lỗi hệ thống FFmpeg: {error_msg}")

        if not os.path.exists(output_video) or os.path.getsize(output_video) == 0:
            raise Exception("Render thất bại: Tên file gốc chứa ký tự không hợp lệ hoặc FFmpeg bị sập ngầm.")
            
        return output_video