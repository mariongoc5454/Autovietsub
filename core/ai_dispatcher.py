from google import genai
from openai import OpenAI

class AIDispatcher:
    def __init__(self, key_manager, logger_callback):
        self.key_manager = key_manager
        self.log = logger_callback
        self.total_tokens_used = 0
        
    def call_api(self, prompt, primary_model):
        m_lower = primary_model.lower()
        primary_provider = "gpt4omini"
        if "gemini" in m_lower: primary_provider = "gemini"
        elif "deepseek" in m_lower: primary_provider = "deepseek"
        elif "mini" in m_lower: primary_provider = "gpt4omini"
        elif "gpt-4o" in m_lower: primary_provider = "gpt4o"

        chain = [(primary_provider, primary_model)]
        defaults = [
            ("gpt4omini", "gpt-4o-mini"),
            ("gemini", "gemini-3.5-flash-lite"),
            ("deepseek", "DeepSeek-V3-0324"),
            ("gpt4o", "gpt-4o")
        ]
        for p, m in defaults:
            if p != primary_provider: chain.append((p, m))
                
        for provider, model_name in chain:
            available_keys = self.key_manager.keys.get(provider, [])
            if not available_keys: continue
            
            for key in available_keys:
                try:
                    if provider == "gemini":
                        client = genai.Client(api_key=key)
                        response = client.models.generate_content(model=model_name, contents=prompt)
                        text = response.text.strip()
                    else:
                        if provider == "deepseek":
                            b_url = "https://api.deepseek.com"
                        elif provider != "openai":
                            b_url = "https://models.inference.ai.azure.com"
                        else:
                            b_url = None
                        
                        client = OpenAI(api_key=key, base_url=b_url)
                        response = client.chat.completions.create(model=model_name, messages=[{"role": "user", "content": prompt}], temperature=0.6)
                        text = response.choices[0].message.content.strip()
                    
                    self.total_tokens_used += (len(prompt) + len(text)) // 4
                    return text, model_name, True
                except Exception as e:
                    self.log(f"⚠️ {model_name} lỗi: {str(e)}. Chuyển đổi tự động...")
                    continue
                    
        return "", None, False