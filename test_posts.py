import sys
from main import create_post_image, ensure_disclaimer

def test_generate():
    print("[Test] Generating sample image for News (お知らせ)...")
    news_title = "【お知らせ】夏季休診期間および診療体制変更のご案内"
    news_img = create_post_image(news_title, "news", "test_news_post.jpg")

    print("[Test] Generating sample image for Sugar (糖のお話)...")
    sugar_title = "【糖のお話】糖尿病と酷暑対策！夏に気をつけたい食生活"
    sugar_img = create_post_image(sugar_title, "sugar", "test_sugar_post.jpg")

    print(f"[Success] Created {news_img} and {sugar_img}")

if __name__ == "__main__":
    test_generate()
