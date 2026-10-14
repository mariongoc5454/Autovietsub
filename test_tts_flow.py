import unittest
import asyncio
from unittest.mock import MagicMock, patch
import edge_tts
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines.translator_engine import TranslatorEngine
from engines.tts_engine import TTSEngine

class TestTTSFlow(unittest.TestCase):
    
    def setUp(self):
        self.dispatcher_mock = MagicMock()
        self.cache_mock = MagicMock()
        self.cache_mock.get.return_value = None
        self.logger_mock = MagicMock()
        
        self.translator = TranslatorEngine(self.dispatcher_mock, self.cache_mock, self.logger_mock)
        self.tts = TTSEngine("ffmpeg", self.logger_mock)
        
    @patch('edge_tts.list_voices')
    def test_voice_validation_vietnamese(self, mock_list_voices):
        # E. Voice tiếng Việt không tồn tại hoặc TTS lỗi -> Báo lỗi rõ ràng
        mock_list_voices.return_value = asyncio.Future()
        mock_list_voices.return_value.set_result([
            {'ShortName': 'vi-VN-HoaiMyNeural', 'Locale': 'vi-VN'},
            {'ShortName': 'zh-CN-XiaoxiaoNeural', 'Locale': 'zh-CN'}
        ])
        
        # Test 1: vi-VN Voice (Valid)
        # Should not raise Exception for voice validation
        self.tts.generate_dubbing([], [], "dummy.mp4", "vi-VN-HoaiMyNeural", MagicMock())
        
        # Test 2: zh-CN Voice (Invalid Locale)
        res2 = self.tts.generate_dubbing([], [], "dummy.mp4", "zh-CN-XiaoxiaoNeural", MagicMock())
        self.assertIsNone(res2)
            
        # Test 3: Non-existent Voice
        res3 = self.tts.generate_dubbing([], [], "dummy.mp4", "vi-VN-FakeVoice", MagicMock())
        self.assertIsNone(res3)

    def test_translator_fallback_empty_string(self):
        # C. Văn bản dịch rỗng -> không tạo audio bằng transcript gốc một cách âm thầm
        # Giả lập model trả về thiếu dòng
        self.dispatcher_mock.call_api.return_value = ("1| Xin chào", "model", True)
        
        Segment = type('Segment', (), {'start': 0.0, 'end': 1.0, 'text': '你好'})
        segments = [Segment(), Segment()] # 2 segments, but API only returns 1
        segments[1].text = '世界'
        
        results = self.translator.process_smart_batch(segments, "", "gpt4o")
        
        self.assertEqual(results[0], "Xin chào")
        self.assertEqual(results[1], "") # MUST be empty string, NOT '世界'

    def test_translator_total_failure(self):
        # D. Translator thất bại -> không tự chuyển sang voice tiếng Trung
        self.dispatcher_mock.call_api.return_value = ("", "model", False)
        Segment = type('Segment', (), {'start': 0.0, 'end': 1.0, 'text': '你好'})
        
        with self.assertRaisesRegex(Exception, "Tất cả API dịch đều thất bại"):
            self.translator.process_smart_batch([Segment()], "", "gpt4o")

if __name__ == '__main__':
    unittest.main()
