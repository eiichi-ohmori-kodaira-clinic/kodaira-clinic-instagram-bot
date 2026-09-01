import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from google import genai
from PIL import Image, ImageDraw, ImageFont

# --- 定数および設定 ---
SITE_URL = "https://kodaira.clinic/"
DISCLAIMER_TEXT = "※本投稿は情報提供を目的としており、個別の診断・治療は医師にご相談ください。"
SEEN_HASHES_FILE = Path("seen_hashes.json")
POST_URLS_FILE = Path("posted_urls.json")
PENDING_POSTS_FILE = Path("pending_posts.json")
ASSETS_DIR = Path("assets")

NEWS_TEMPLATE_PATH = ASSETS_DIR / "news_template.png"
SUGAR_TEMPLATE_PATH = ASSETS_DIR / "sugar_template.png"

# フォント色設定
NEWS_COLOR = (230, 81, 0)     # オレンジ (お知らせ)
SUGAR_COLOR = (46, 125, 50)   # グリーン (糖のお話)

# --- 免責事項ハードガードレール ---
def ensure_disclaimer(caption: str) -> str:
    if DISCLAIMER_TEXT not in caption:
        caption = caption.strip() + "\n\n" + DISCLAIMER_TEXT
    return caption

def calculate_hash(key_string: str) -> str:
    return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

def load_seen_hashes() -> set:
    if SEEN_HASHES_FILE.exists():
        try:
            with open(SEEN_HASHES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_hashes(hashes: set):
    with open(SEEN_HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sorted(hashes)), f, ensure_ascii=False, indent=2)

def save_posted_url(data: dict):
    urls = []
    if POST_URLS_FILE.exists():
        try:
            with open(POST_URLS_FILE, "r", encoding="utf-8") as f:
                urls = json.load(f)
        except Exception:
            urls = []
    urls.append(data)
    with open(POST_URLS_FILE, "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)

def get_japanese_font(font_size: int = 48):
    font_candidates = [
        "C:\\Windows\\Fonts\\meiryo.ttc",
        "C:\\Windows\\Fonts\\msgothic.ttc",
        "C:\\Windows\\Fonts\\yuGothM.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines

def create_post_image(title: str, category: str, output_path: str = "post_image.jpg") -> str:
    img_width, img_height = 1080, 1350
    template_path = SUGAR_TEMPLATE_PATH if category == "sugar" else NEWS_TEMPLATE_PATH
    text_color = SUGAR_COLOR if category == "sugar" else NEWS_COLOR

    if template_path.exists():
        base_img = Image.open(template_path).convert("RGB")
        if base_img.size != (img_width, img_height):
            base_img = base_img.resize((img_width, img_height), Image.Resampling.LANCZOS)
    else:
        base_img = Image.new("RGB", (img_width, img_height), (245, 247, 248))

    draw = ImageDraw.Draw(base_img)
    font_size = 52
    font = get_japanese_font(font_size)

    max_text_width = 850
    lines = wrap_text(title, font, max_text_width)
    line_height = font_size * 1.5
    total_text_height = len(lines) * line_height
    start_y = (img_height - total_text_height) // 2 + 80

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        x = (img_width - w) // 2
        y = start_y + i * line_height
        draw.text((x, y), line, font=font, fill=text_color)

    base_img.save(output_path, "JPEG", quality=95)
    print(f"[Info] Created post image ({category}): {output_path}")
    return output_path

def scrape_kodaira_clinic():
    print(f"[Info] Scraping {SITE_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(SITE_URL, headers=headers, timeout=(5, 30))
        res.raise_for_status()
        res.encoding = res.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"[Error] Failed to fetch {SITE_URL}: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    articles = []

    news_wrapper = soup.find("div", class_="wrapper_news") or soup
    dls = news_wrapper.find_all("dl", class_=re.compile(r"list_news"))
    for dl in dls:
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            dt_classes = dt.get("class", [])
            cat_str = " ".join(dt_classes)
            category = "sugar" if "cat002" in cat_str or "sugar" in dl.get("class", []) else "news"
            
            date_div = dt.find("div", class_="date")
            title_div = dt.find("div", class_="tit")

            date_text = date_div.get_text(strip=True) if date_div else ""
            title_text = title_div.get_text(strip=True) if title_div else ""
            
            for br in dd.find_all("br"):
                br.replace_with("\n")
            body_text = dd.get_text(strip=True)

            if not title_text:
                continue

            key = f"{date_text}_{category}_{title_text}"
            article_hash = calculate_hash(key)

            articles.append({
                "hash": article_hash,
                "category": category,
                "date": date_text,
                "title": title_text,
                "body": body_text
            })

    unique_articles = []
    seen = set()
    for item in articles:
        if item["hash"] not in seen:
            seen.add(item["hash"])
            unique_articles.append(item)

    print(f"[Info] Found {len(unique_articles)} articles.")
    return unique_articles

def generate_caption_with_gemini(article: dict) -> str:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    category_label = "【糖のお話】" if article["category"] == "sugar" else "【お知らせ】"

    if not gemini_api_key:
        print("[Warning] GEMINI_API_KEY is missing. Using fallback caption.")
        caption = f"{category_label} {article['title']}\n\n{article['body']}\n\n#小平内科糖尿病クリニック #内科 #糖尿病"
        return ensure_disclaimer(caption)

    prompt = f"""
あなたは「小平内科糖尿病クリニック」のInstagram広報担当です。
以下のWebサイトの新着記事を元に、Instagram向けの親しみやすく読みやすい投稿文（キャプション）を作成してください。

タイトル: {article['title']}
日付: {article['date']}
カテゴリ: {category_label}
本文:
{article['body']}

■ 投稿作成ルール:
1. 冒頭に {category_label} およびタイトルを記載。
2. 専門用語をわかりやすく解説し、患者様や一般の方が親しみやすい丁寧な敬語（〜です、〜ます）を使用。
3. 医療広告ガイドラインを遵守し、断定的な治療効果の保証や過剰な宣伝表現は避ける。
4. 適切な絵文字や改行を入れて読みやすく装飾する。
5. 文末にハッシュタグ（#小平内科糖尿病クリニック #糖尿病 #健康 #小平市 など）を追加。
"""

    try:
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model="gemini-3.7-flash",
            contents=prompt
        )
        caption = response.text.strip()
    except Exception as e:
        print(f"[Error] Gemini API generation failed: {e}")
        caption = f"{category_label} {article['title']}\n\n{article['body']}\n\n#小平内科糖尿病クリニック"

    return ensure_disclaimer(caption)

def post_to_instagram(image_path: str, caption: str, title: str = "") -> dict:
    ig_user_id = os.environ.get("IG_USER_ID")
    meta_access_token = os.environ.get("META_ACCESS_TOKEN")

    if not ig_user_id or not meta_access_token:
        print("[Warning] IG_USER_ID or META_ACCESS_TOKEN is missing. Skipping API publish.")
        return {"success": False, "reason": "Missing Credentials"}

    repo_owner = "eiichi-ohmori-kodaira-clinic"
    repo_name = "kodaira-clinic-instagram-bot"
    image_raw_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/{image_path}"

    print(f"[Info] Publishing image to Instagram via Meta Graph API...")
    print(f"[Info] Image URL: {image_raw_url}")

    # 1. コンテナ作成
    container_url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media"
    params = {
        "image_url": image_raw_url,
        "caption": caption,
        "access_token": meta_access_token
    }
    try:
        res = requests.post(container_url, data=params, timeout=30)
        res_data = res.json()
        print(f"[Debug] Container API Response: {res_data}")
        if "id" not in res_data:
            print(f"[Error] Failed to create media container: {res_data}")
            return {"success": False, "response": res_data}
        container_id = res_data["id"]
        print(f"[Info] Media container created: {container_id}")
    except Exception as e:
        print(f"[Error] Container API error: {e}")
        return {"success": False, "error": str(e)}

    # 2. ポーリング
    status_url = f"https://graph.facebook.com/v20.0/{container_id}"
    status_params = {"fields": "status_code", "access_token": meta_access_token}
    
    for attempt in range(10):
        time.sleep(5)
        try:
            st_res = requests.get(status_url, params=status_params, timeout=15)
            st_data = st_res.json()
            status_code = st_data.get("status_code")
            print(f"[Info] Polling status ({attempt + 1}/10): {status_code}")
            if status_code == "FINISHED":
                break
            elif status_code in ["ERROR", "EXPIRED"]:
                print(f"[Error] Container processing failed with status: {status_code}")
                return {"success": False, "response": st_data}
        except Exception as e:
            print(f"[Warning] Polling request error: {e}")

    # 3. 公開
    publish_url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media_publish"
    pub_params = {
        "creation_id": container_id,
        "access_token": meta_access_token
    }
    try:
        pub_res = requests.post(publish_url, data=pub_params, timeout=30)
        pub_data = pub_res.json()
        print(f"[Debug] Publish API Response: {pub_data}")
        if "id" in pub_data:
            media_id = pub_data["id"]
            print(f"[Success] Instagram post published! Post ID: {media_id}")
            
            permalink_url = f"https://graph.facebook.com/v20.0/{media_id}"
            p_res = requests.get(permalink_url, params={"fields": "permalink", "access_token": meta_access_token}, timeout=15)
            p_data = p_res.json()
            permalink = p_data.get("permalink", f"https://www.instagram.com/p/{media_id}/")
            print(f"[Success] Instagram Post Direct URL (Permalink): {permalink}")
            
            save_posted_url({"title": title, "id": media_id, "permalink": permalink})
            return {"success": True, "media_id": media_id, "permalink": permalink}
        else:
            print(f"[Error] Publish failed: {pub_data}")
            return {"success": False, "response": pub_data}
    except Exception as e:
        print(f"[Error] Publish API error: {e}")
        return {"success": False, "error": str(e)}

def mode_prepare():
    """ステップ1: 記事をパースして画像とキャプションを生成"""
    print("[Info] Mode: PREPARE (Generate images and captions)")
    seen_hashes = load_seen_hashes()
    articles = scrape_kodaira_clinic()

    target_news = None
    target_sugar = None

    for article in articles:
        if article["hash"] in seen_hashes:
            continue
        if article["category"] == "news" and not target_news:
            target_news = article
        elif article["category"] == "sugar" and not target_sugar:
            target_sugar = article
        
        if target_news and target_sugar:
            break

    targets = [a for a in [target_news, target_sugar] if a is not None]

    if not targets:
        print("[Info] No new unposted articles found.")
        with open(PENDING_POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    pending = []
    for article in targets:
        image_name = f"post_{article['category']}.jpg"
        create_post_image(article["title"], article["category"], image_name)
        caption = generate_caption_with_gemini(article)
        pending.append({
            "article": article,
            "image_path": image_name,
            "caption": caption
        })

    with open(PENDING_POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    print(f"[Info] Prepared {len(pending)} pending posts in {PENDING_POSTS_FILE}")

def mode_publish():
    """ステップ2: GitHubにプッシュされた画像を Meta Graph API へ投稿"""
    print("[Info] Mode: PUBLISH (Publish to Instagram)")
    if not PENDING_POSTS_FILE.exists():
        print("[Info] No pending_posts.json found.")
        return

    try:
        with open(PENDING_POSTS_FILE, "r", encoding="utf-8") as f:
            pending = json.load(f)
    except Exception as e:
        print(f"[Error] Failed to read pending posts: {e}")
        return

    if not pending:
        print("[Info] Pending posts list is empty.")
        return

    seen_hashes = load_seen_hashes()
    posted_count = 0

    for item in pending:
        article = item["article"]
        image_path = item["image_path"]
        caption = item["caption"]

        print(f"\n[Info] Publishing '{article['category']}': '{article['title']}'...")
        result = post_to_instagram(image_path, caption, title=article["title"])

        if result.get("success"):
            seen_hashes.add(article["hash"])
            posted_count += 1
            time.sleep(3)
        else:
            print(f"[Warning] API publish was not successful: {result}")

    save_seen_hashes(seen_hashes)
    print(f"\n[Info] Publish mode finished. Processed {posted_count} posts.")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "prepare":
        mode_prepare()
    elif mode == "publish":
        mode_publish()
    else:
        mode_prepare()
        mode_publish()

if __name__ == "__main__":
    main()
