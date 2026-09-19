import os

class KeyManager:
    def __init__(self, filepath="api_keys.txt"):
        self.filepath = filepath
        self.keys = {"gemini": [], "gpt4o": [], "gpt4omini": [], "deepseek": []}
        self.load_keys()
        
    def load_keys(self):
        if not os.path.exists(self.filepath): return
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line in f.read().splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                
                if ":" in line: prefix, key = line.split(":", 1)
                elif "=" in line: prefix, key = line.split("=", 1)
                else: continue
                
                prefix = prefix.strip().lower().replace("_", "").replace("-", "")
                key = key.strip()
                if not key: continue
                
                if "gemini" in prefix: self.keys["gemini"].append(key)
                elif "gpt4omini" in prefix or "mini" in prefix: self.keys["gpt4omini"].append(key)
                elif "gpt4o" in prefix: self.keys["gpt4o"].append(key)
                elif "deepseek" in prefix: self.keys["deepseek"].append(key)