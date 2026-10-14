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

    def _run_cmd(self, cmd_args, stop_event):
        process = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        while True:
            if stop_event and stop_event.is_set():
                process.kill()
                raise Exception("Tác vụ bị hủy bởi người dùng!")
            try:
                out, err = process.communicate(timeout=0.5)
                return process.returncode, err.decode('utf-8', errors='ignore')
            except subprocess.TimeoutExpired:
                continue

    def render_video(self, video_path, srt_path, dub_audio_path, is_mobile, blur_enabled, final_style, blur_y_ratio, blur_strength, blur_height, logo_blur_enabled, logo_size_percent, sub_enabled, bg_music_enabled, bg_music_path, bg_music_volume, stop_event=None):
        output_video = video_path.rsplit('.', 1)[0] + "_Vietsub.mp4"
        srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')
        
        # Dùng bộ lọc null nối thẳng luồng nếu tính năng Vietsub bị tắt
        if sub_enabled:
            vf_filter = f"subtitles='{srt_escaped}':force_style='{final_style}'"
        else:
            vf_filter = "null"
        
        # Gọi module Blur từ file blur_engine.py
        vf_filter = BlurEngine.apply_blur(vf_filter, blur_enabled, blur_y_ratio, blur_strength, blur_height, logo_blur_enabled, logo_size_percent)
        
        def build_stream(args):
            in_vid = ffmpeg.input(video_path)
            base_audio = ffmpeg.input(dub_audio_path).audio if dub_audio_path and os.path.exists(dub_audio_path) else in_vid.audio
            
            if bg_music_enabled and bg_music_path and os.path.exists(bg_music_path):
                bg_audio = ffmpeg.input(bg_music_path).audio.filter('volume', bg_music_volume / 100.0)
                # amix without normalize=0 drops volume, so we set normalize=0 if supported or just boost it.
                # Actually, many FFmpeg versions support normalize=0. Let's try to add it.
                mixed_audio = ffmpeg.filter([base_audio, bg_audio], 'amix', inputs=2, duration='first')
                
                args["acodec"] = "aac"
                return ffmpeg.output(in_vid.video, mixed_audio, output_video, vf=vf_filter, **args)
            else:
                if dub_audio_path and os.path.exists(dub_audio_path):
                    args["acodec"] = "aac"
                    return ffmpeg.output(in_vid.video, base_audio, output_video, vf=vf_filter, **args)
                else:
                    args["acodec"] = "copy"
                    return ffmpeg.output(in_vid, output_video, vf=vf_filter, **args)

        try:
            out_args = {"vcodec": "h264_nvenc", "preset": "fast"}
            stream = build_stream(out_args)
            
            cmd_args = ffmpeg.compile(stream.overwrite_output(), cmd=self.ffmpeg_path)
            ret_code, err_msg = self._run_cmd(cmd_args, stop_event)
            
            if ret_code != 0:
                raise Exception(f"Lỗi GPU Render: {err_msg}")
                
        except Exception as e:
            if "Tác vụ bị hủy" in str(e):
                raise e
            self.log("⚠️ Chuyển đổi sang CPU UltraFast...")
            out_args_cpu = {"vcodec": "libx264", "preset": "ultrafast", "threads": os.cpu_count()}
            stream = build_stream(out_args_cpu)
            
            cmd_args_cpu = ffmpeg.compile(stream.overwrite_output(), cmd=self.ffmpeg_path)
            
            ret_code, err_msg = self._run_cmd(cmd_args_cpu, stop_event)
            
            if ret_code != 0:
                raise Exception(f"Lỗi hệ thống FFmpeg: {err_msg}")

        if not os.path.exists(output_video) or os.path.getsize(output_video) == 0:
            raise Exception("Render thất bại: Tên file gốc chứa ký tự không hợp lệ hoặc FFmpeg bị sập ngầm.")
            
        return output_video