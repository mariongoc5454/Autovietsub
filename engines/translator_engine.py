import re
import time

class TranslatorEngine:
    def __init__(self, dispatcher, cache, logger):
        self.dispatcher = dispatcher
        self.cache = cache
        self.log = logger

    def process_smart_batch(self, batch_segments, context_str, primary_model, stop_event=None):
        if stop_event and stop_event.is_set():
            raise Exception("Tác vụ bị hủy bởi người dùng!")
            
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
        
        prompt = f"""Bạn là một chuyên gia Đạo diễn kiêm Biên dịch video lồng tiếng.
CẢNH BÁO: Phụ đề gốc có thể sai do AI nhận diện nhầm. Hãy dùng NGỮ CẢNH để tự sửa lỗi và dịch cho hợp lý.

[NGỮ CẢNH VIDEO (Các câu hội thoại xung quanh)]:
"{context_str}"

[NHIỆM VỤ DỊCH & CĂN CHỈNH THỜI GIAN]:
Dựa SÁT VÀO NGỮ CẢNH trên, hãy dịch các câu sau sang Tiếng Việt.
YÊU CẦU QUAN TRỌNG NHẤT: 
1. Bám sát ngữ cảnh, ĐỒNG BỘ ĐẠI TỪ NHÂN XƯNG (anh/em, mày/tao, tôi/cậu...) xuyên suốt đoạn hội thoại. Ngôn từ tự nhiên, văn nói.
2. THỜI LƯỢNG (s): Tốc độ đọc lồng tiếng chuẩn là 3-4 từ/giây. Nếu thời lượng (s) quá ngắn, PHẢI CHỦ ĐỘNG RÚT GỌN CÔ ĐỌNG TỪ VỰNG sao cho khớp số giây mà KHÔNG làm đổi ý chính.

DANH SÁCH CÁC CÂU CẦN DỊCH:
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
                    text_part = match.group(2).strip()
                    # Xóa phần thời lượng AI có thể chèn vào (vd: "(1.5s)", "[1.5s]", "1.5s")
                    text_part = re.sub(r'^[\(\[]\s*\d+(?:[\.,]\d+)?\s*[sS]?\s*[\)\]]\s*', '', text_part)
                    text_part = re.sub(r'^\d+(?:[\.,]\d+)?\s*[sS]\s+', '', text_part)
                    # Xóa chỉ mục bị lặp lại nếu có (vd AI trả về "1| 1. Xin chào")
                    text_part = re.sub(r'^\d+\s*(?:[\|\]\)\:]|\.(?=\s)|\-(?=\s))\s*', '', text_part)
                    split_translated[int(match.group(1)) - 1] = text_part

        if not success:
            raise Exception("Tất cả API dịch đều thất bại hoặc hết Rate Limit! Không thể tiếp tục.")

        for dict_idx, (original_idx, original_text, _) in enumerate(need_translation):
            res = split_translated.get(dict_idx)
            if not res:
                self.log(f"⚠️ Cảnh báo: AI không trả về bản dịch cho câu: '{original_text}'. Bỏ trống để tránh đọc nhầm ngôn ngữ gốc.")
                res = ""
            else:
                self.cache.set(original_text, res)
            final_results[original_idx] = res
            
        return final_results