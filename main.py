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
HASHTAGS_TEXT = "#小平市 #内科 #糖尿病"
SEEN_HASHES_FILE = Path("seen_hashes.json")
POST_URLS_FILE = Path("posted_urls.json")
PENDING_POSTS_FILE = Path("pending_posts.json")
EXEC_LOG_FILE = Path("execution_log.txt")
ASSETS_DIR = Path("assets")

NEWS_COLOR = (255, 102, 0)     # 明るいオレンジ (お知らせ)
SUGAR_COLOR = (40, 180, 70)    # 明るいグリーン (糖のお話)

# Instagram 標準画像サイズ (1080 x 1080 px 正方形)
CANVAS_SIZE = 1080

def log_debug(message: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_str = f"[{timestamp}] {message}"
    print(log_str)
    with open(EXEC_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_str + "\n")

def ensure_disclaimer(caption: str) -> str:
    """キャプション末尾に指定ハッシュタグおよび免責事項を確実に付与する"""
    caption = caption.strip()
    caption = re.sub(r"(#[\w一-龠ぁ-んァ-ヶー]+\s*)+$", "", caption).strip()
    caption = f"{caption}\n\n{HASHTAGS_TEXT}\n\n{DISCLAIMER_TEXT}"
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

def get_japanese_font(font_size: int = 110):
    """Linux(GitHub Actions)およびWindowsの日本語フォントを確実に読み込む"""
    font_candidates = [
        # 同梱・ローカルフォント
        ASSETS_DIR / "fonts" / "meiryo.ttc",
        ASSETS_DIR / "fonts" / "JapaneseFont.ttf",
        # Linux (Ubuntu apt-get fonts-noto-cjk / fonts-ipafont-gothic) パス
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        # Windows パス
        "C:\\Windows\\Fonts\\meiryo.ttc",
        "C:\\Windows\\Fonts\\msgothic.ttc",
        "C:\\Windows\\Fonts\\yuGothM.ttc",
    ]
    for font_path in font_candidates:
        font_str = str(font_path)
        if os.path.exists(font_str):
            try:
                font = ImageFont.truetype(font_str, font_size)
                log_debug(f"Loaded font successfully: {font_str} (size: {font_size})")
                return font
            except Exception as e:
                log_debug(f"Failed loading font {font_str}: {e}")
                continue
    
    log_debug("WARNING: No CJK Japanese font found. Falling back to default.")
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

def clean_title_for_display(title: str, category: str) -> str:
    """画像のテンプレート背景に合わせてタイトル文字列を調整する"""
    display_title = title.strip()
    if category == "sugar":
        # 【糖のお話】や【お知らせ】のカテゴリプレフィックスを除去
        display_title = re.sub(r"^【?(糖のお話|お知らせ)】?\s*[\s　:-]*", "", display_title)
        # 糖のお話タイトルの「糖尿病」を含めない
        display_title = re.sub(r"^糖尿病\s*[\s　:-]*", "", display_title)
    return display_title

def find_template_file(base_name: str) -> Path:
    """拡張子 (.png, .jpg, .jpeg 等) を自動探索してテンプレート画像パスを返す"""
    for ext in [".png", ".jpg", ".jpeg", ".PNG", ".JPG"]:
        p = ASSETS_DIR / f"{base_name}{ext}"
        if p.exists():
            return p
    return None

def prepare_square_template(template_path: Path, target_size: int = 1080) -> Image.Image:
    """元画像を歪ませずに正方形1080x1080キャンバス全面へ完璧にフィットさせたテンプレート画像を返す"""
    if template_path and template_path.exists():
        raw_img = Image.open(template_path).convert("RGBA")
        w, h = raw_img.size
        
        # 1080x1080 キャンバスを埋めるスケール計算
        scale = max(target_size / w, target_size / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        
        resized = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        square_canvas = Image.new("RGBA", (target_size, target_size), (255, 255, 255, 255))
        paste_x = (target_size - new_w) // 2
        paste_y = (target_size - new_h) // 2
        square_canvas.paste(resized, (paste_x, paste_y), resized)
        
        base_img = square_canvas.convert("RGB")
    else:
        base_img = Image.new("RGB", (target_size, target_size), (255, 255, 255))
    return base_img

def create_post_image(title: str, category: str, output_path: str = "post_image.jpg") -> str:
    """正方形1080x1080pxキャンバスで文字太さ倍増・110px超巨大文字タイトル画像を生成"""
    base_name = "sugar_template" if category == "sugar" else "news_template"
    template_path = find_template_file(base_name)
    text_color = SUGAR_COLOR if category == "sugar" else NEWS_COLOR

    # 正方形1080x1080にフィットさせたテンプレート基盤画像
    base_img = prepare_square_template(template_path, target_size=CANVAS_SIZE)

    img_width, img_height = base_img.size
    draw = ImageDraw.Draw(base_img)

    display_title = clean_title_for_display(title, category)
    
    # 文字サイズをさらに大きく110pxに拡大
    font_size = int(img_height * 0.105)  # 1080px上で約113pxの超巨大フォント
    font = get_japanese_font(font_size)

    max_text_width = int(img_width * 0.88)
    lines = wrap_text(display_title, font, max_text_width)
    
    if len(lines) > 2:
        font_size = int(img_height * 0.078)  # 複数行でも約84pxの巨大フォント
        font = get_japanese_font(font_size)
        lines = wrap_text(display_title, font, max_text_width)

    line_height = font_size * 1.30
    total_text_height = len(lines) * line_height

    # カテゴリに応じた下部エリアのテキスト中央位置計算
    if category == "sugar":
        target_center_y = int(img_height * 0.74)
    else:
        target_center_y = int(img_height * 0.78)

    start_y = target_center_y - (total_text_height / 2)

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        w_text = bbox[2] - bbox[0]
        x = (img_width - w_text) // 2
        y = start_y + i * line_height
        
        # ユーザー指定: 「太さは倍に（文字線を同色ストロークで2倍に太化）、縁取りは太くしなくてよい」
        draw.text(
            (x, y),
            line,
            font=font,
            fill=text_color,
            stroke_width=6,              # 文字本体の太さを倍に拡張
            stroke_fill=text_color       # 縁取りではなく文字同色で線自体を太化
        )
        log_debug(f"Drew double-thick line '{line}' at x={x}, y={y} with fill={text_color}")

    base_img.save(output_path, "JPEG", quality=95)
    log_debug(f"Created post image ({category}): {output_path} (final size: {base_img.size})")
    return output_path

def scrape_kodaira_clinic():
    log_debug(f"Scraping {SITE_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(SITE_URL, headers=headers, timeout=(5, 30))
        res.raise_for_status()
        res.encoding = res.apparent_encoding or "utf-8"
    except Exception as e:
        log_debug(f"Failed to fetch {SITE_URL}: {e}")
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

    log_debug(f"Found {len(unique_articles)} articles.")
    return unique_articles

def generate_caption_with_gemini(article: dict) -> str:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    category_label = "【糖のお話】" if article["category"] == "sugar" else "【お知らせ】"

    if not gemini_api_key:
        log_debug("GEMINI_API_KEY is missing. Using fallback caption.")
        caption = f"{category_label} {article['title']}\n\n{article['body']}"
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
5. 本文作成のみを行い、文末のハッシュタグ（#小平市 #内科 #糖尿病）と免責事項は別途自動追加されます。
"""

    models_to_try = ["gemini-3.7-flash", "gemini-flash-latest"]
    for model_name in models_to_try:
        try:
            client = genai.Client(api_key=gemini_api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                return ensure_disclaimer(response.text.strip())
        except Exception as e:
            log_debug(f"Gemini API generation with {model_name} failed: {e}")
            time.sleep(2)

    log_debug("Using fallback caption after Gemini models unavailable.")
    caption = f"{category_label} {article['title']}\n\n{article['body']}"
    return ensure_disclaimer(caption)

def post_to_instagram(image_path: str, caption: str, title: str = "") -> dict:
    ig_user_id = os.environ.get("IG_USER_ID")
    meta_access_token = os.environ.get("META_ACCESS_TOKEN")

    log_debug(f"Checking credentials: IG_USER_ID exists={bool(ig_user_id)}, META_ACCESS_TOKEN exists={bool(meta_access_token)}")

    if not ig_user_id or not meta_access_token:
        log_debug("ERROR: IG_USER_ID or META_ACCESS_TOKEN is missing. Aborting publish.")
        return {"success": False, "reason": "Missing Credentials"}

    repo_owner = "eiichi-ohmori-kodaira-clinic"
    repo_name = "kodaira-clinic-instagram-bot"
    image_raw_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/{image_path}"

    log_debug(f"Publishing image to Instagram via Meta Graph API...")
    log_debug(f"Target IG_USER_ID: {ig_user_id}")
    log_debug(f"Image URL: {image_raw_url}")

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
        log_debug(f"Container API Response: {res_data}")
        if "id" not in res_data:
            log_debug(f"ERROR: Failed to create media container. Meta API Response: {res_data}")
            return {"success": False, "response": res_data}
        container_id = res_data["id"]
        log_debug(f"Media container created successfully. ID: {container_id}")
    except Exception as e:
        log_debug(f"ERROR: Container API Exception: {e}")
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
            log_debug(f"Polling status ({attempt + 1}/10): {status_code} (Full: {st_data})")
            if status_code == "FINISHED":
                break
            elif status_code in ["ERROR", "EXPIRED"]:
                log_debug(f"ERROR: Container processing failed with status: {status_code}. Response: {st_data}")
                return {"success": False, "response": st_data}
        except Exception as e:
            log_debug(f"Polling Exception: {e}")

    # 3. 公開
    publish_url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media_publish"
    pub_params = {
        "creation_id": container_id,
        "access_token": meta_access_token
    }
    try:
        pub_res = requests.post(publish_url, data=pub_params, timeout=30)
        pub_data = pub_res.json()
        log_debug(f"Publish API Response: {pub_data}")
        if "id" in pub_data:
            media_id = pub_data["id"]
            log_debug(f"SUCCESS: Instagram post published! Post ID: {media_id}")
            
            permalink_url = f"https://graph.facebook.com/v20.0/{media_id}"
            p_res = requests.get(permalink_url, params={"fields": "permalink", "access_token": meta_access_token}, timeout=15)
            p_data = p_res.json()
            permalink = p_data.get("permalink", f"https://www.instagram.com/p/{media_id}/")
            log_debug(f"SUCCESS: Instagram Post Direct URL (Permalink): {permalink}")
            
            save_posted_url({"title": title, "id": media_id, "permalink": permalink})
            return {"success": True, "media_id": media_id, "permalink": permalink}
        else:
            log_debug(f"ERROR: Publish failed. Response: {pub_data}")
            return {"success": False, "response": pub_data}
    except Exception as e:
        log_debug(f"ERROR: Publish API Exception: {e}")
        return {"success": False, "error": str(e)}

def mode_prepare():
    log_debug("=== MODE: PREPARE ===")
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
        log_debug("No new unposted articles found.")
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
    log_debug(f"Prepared {len(pending)} pending posts in {PENDING_POSTS_FILE}")

def mode_publish():
    log_debug("=== MODE: PUBLISH ===")
    if not PENDING_POSTS_FILE.exists():
        log_debug("No pending_posts.json found.")
        return

    try:
        with open(PENDING_POSTS_FILE, "r", encoding="utf-8") as f:
            pending = json.load(f)
    except Exception as e:
        log_debug(f"Failed to read pending posts: {e}")
        return

    if not pending:
        log_debug("Pending posts list is empty.")
        return

    seen_hashes = load_seen_hashes()
    posted_count = 0

    for item in pending:
        article = item["article"]
        image_path = item["image_path"]
        caption = item["caption"]

        log_debug(f"Publishing '{article['category']}': '{article['title']}'...")
        result = post_to_instagram(image_path, caption, title=article["title"])

        if result.get("success"):
            seen_hashes.add(article["hash"])
            posted_count += 1
            time.sleep(3)
        else:
            log_debug(f"Publish failed for '{article['title']}': {result}")

    save_seen_hashes(seen_hashes)
    log_debug(f"Publish mode finished. Successfully published {posted_count} posts.")

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
