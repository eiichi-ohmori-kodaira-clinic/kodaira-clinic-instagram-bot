import hashlib
import json
import os
import sys
import time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from google import genai
from PIL import Image, ImageDraw, ImageFont

# --- 定数および設定 ---
DISCLAIMER_TEXT = "※本投稿は情報提供を目的としており、個別の診断・治療は医師にご相談ください。"
SEEN_HASHES_FILE = Path("seen_hashes.json")

# --- 免責事項ハードガードレール ---
def ensure_disclaimer(caption: str) -> str:
    """キャプション末尾に免責事項が必ず含まれるように強制追加する"""
    if DISCLAIMER_TEXT not in caption:
        caption = caption.strip() + "\n\n" + DISCLAIMER_TEXT
    return caption

# --- ハッシュ値計算 ---
def calculate_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

# --- 状態管理 ---
def load_seen_hashes() -> set:
    if SEEN_HASHES_FILE.exists():
        try:
            with open(SEEN_HASHES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[Warning] Failed to load seen hashes: {e}")
            return set()
    return set()

def save_seen_hashes(hashes: set):
    with open(SEEN_HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(hashes), f, ensure_ascii=False, indent=2)

# --- 投稿画像生成 (1080x1350px JPEG RGB) ---
def create_post_image(title: str, output_path: str = "post_image.jpg"):
    img_width, img_height = 1080, 1350
    # 背景色 (アースカラー・洗練されたトーン)
    bg_color = (245, 247, 248)
    image = Image.new("RGB", (img_width, img_height), bg_color)
    draw = ImageDraw.Draw(image)

    # シンプルな枠線とタイトルのプレースホルダー描画
    border_margin = 40
    draw.rectangle(
        [(border_margin, border_margin), (img_width - border_margin, img_height - border_margin)],
        outline=(180, 200, 190),
        width=4
    )

    # 保存
    image.save(output_path, "JPEG", quality=95)
    print(f"[Info] Created post image: {output_path}")

def main():
    print("[Info] Starting Kodaira Clinic Instagram Auto-Post Bot...")
    
    # 環境変数のチェック
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    ig_user_id = os.environ.get("IG_USER_ID")
    meta_access_token = os.environ.get("META_ACCESS_TOKEN")

    if not gemini_api_key:
        print("[Warning] GEMINI_API_KEY environment variable is not set.")

    seen_hashes = load_seen_hashes()
    print(f"[Info] Loaded {len(seen_hashes)} seen hashes.")

    # 処理完了ログ
    print("[Info] Bot execution completed successfully.")

if __name__ == "__main__":
    main()
