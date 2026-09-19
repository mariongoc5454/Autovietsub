import re
import time

class TranslatorEngine:
    def __init__(self, dispatcher, cache, logger):
        self.dispatcher = dispatcher
        self.cache = cache
        self.log = logger

    def process_smart_batch(self, batch_segments, context_str, primary_model):
        need_translation = []
        final_results = [None] * len(batch_segments)
        
        for i, seg in enumerate(batch_segments):
            cached_text = self.cache.get(seg.text)
            if cached_text: 
                final_results[i] = cached_text
            else: 
                duration = seg.end - seg.start
                need_translation.append((i, seg.text.strip(), duration))
                
        if not need_translation: 
            return final_results

        batch_text_prompt = "\n".join([f"{idx+1}| ({dur:.1f}s) {text}" for idx, (_, text, dur) in enumerate(need_translation)])
        
        prompt = f"""Bạn là một chuyên gia Đạo diễn kiêm Biên dịch video ngắn lồng tiếng.
CẢNH BÁO: Bóc băng gốc có thể sai lệch do tiếng địa phương. Dùng logic cốt truyện để tự sửa lỗi cho hợp lý bối cảnh.

[CỐT TRUYỆN ĐOẠN VIDEO]: "{context_str}"

[NHIỆM VỤ DỊCH & CĂN CHỈNH THỜI GIAN]:
Dịch các câu sau sang Tiếng Việt (Tự nhiên, hài hước, văn nói).
ĐẶC BIỆT CHÚ Ý THỜI LƯỢNG (s): Tốc độ đọc lồng tiếng chuẩn là khoảng 3-4 từ Tiếng Việt/giây. 
Nếu thời lượng quá ngắn mà câu gốc quá dài, BẠN PHẢI CHỦ ĐỘNG RÚT GỌN, CÔ ĐỌNG TỪ VỰNG (paraphrase) sao cho khớp với số giây (để AI lồng tiếng có thể đọc với tốc độ bình thường), nhưng TUYỆT ĐỐI GIỮ NGUYÊN Ý NGHĨA VÀ NỘI DUNG GỐC, không được thêm bớt tình tiết.

{batch_text_prompt}

[BẮT BUỘC]: Trả về đúng {len(need_translation)} dòng theo định dạng sau (không giải thích thêm):
1| [Tiếng Việt]
2| [Tiếng Việt]"""

        translated_raw, used_model, success = self.dispatcher.call_api(prompt, primary_model)
        
        split_translated = {}
        if success:
            for line in translated_raw.split('\n'):
                # Mở rộng Regex: Bắt mọi định dạng "1|", "1.", "1:", "1-", "1)"
                match = re.match(r'^\s*(\d+)\s*[\.\|\]\)\:\-]\s*(.*)', line.strip())
                if match: 
                    split_translated[int(match.group(1)) - 1] = match.group(2).strip()

        for dict_idx, (original_idx, original_text, _) in enumerate(need_translation):
            res = split_translated.get(dict_idx, original_text)
            final_results[original_idx] = res
            self.cache.set(original_text, res)
            
        return final_results