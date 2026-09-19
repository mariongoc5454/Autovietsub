import sqlite3
import hashlib

class CacheManager:
    def __init__(self, db_path="translation_cache.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS translations (
                text_hash TEXT PRIMARY KEY, 
                source_text TEXT, 
                translated_text TEXT
            )
        ''')
        self.conn.commit()

    def _hash(self, text):
        return hashlib.md5(text.strip().encode('utf-8')).hexdigest()

    def get(self, text):
        self.cursor.execute("SELECT translated_text FROM translations WHERE text_hash=?", (self._hash(text),))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def set(self, text, translated_text):
        if not translated_text: return
        self.cursor.execute("INSERT OR REPLACE INTO translations (text_hash, source_text, translated_text) VALUES (?, ?, ?)", 
                            (self._hash(text), text.strip(), translated_text.strip()))
        self.conn.commit()