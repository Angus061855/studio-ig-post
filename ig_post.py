import os
import time
import requests
import cloudinary
import cloudinary.uploader
import google.genai as genai

# ── 環境變數 ──────────────────────────────────────────
NOTION_TOKEN          = os.environ["NOTION_API_KEY"]
DATABASE_ID           = os.environ["NOTION_DATABASE_ID_IG"]
IG_USER_ID            = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN       = os.environ["IG_ACCESS_TOKEN"]
CLOUDINARY_CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
CLOUDINARY_API_KEY    = os.environ["CLOUDINARY_API_KEY"]
CLOUDINARY_API_SECRET = os.environ["CLOUDINARY_API_SECRET"]
GEMINI_API_KEY        = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN        = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID      = os.environ["TELEGRAM_CHAT_ID"]

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# ── Notion：取得待發項目 ──────────────────────────────
def get_pending_post():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=headers, json={
        "filter": {
            "property": "狀態",
            "status": { "equals": "待發" }
        },
        "page_size": 1
    })
    results = res.json().get("results", [])
    print(f"找到 {len(results)} 筆待發項目")
    return results[0] if results else None

# ── Notion：取得圖片 URL 清單 ─────────────────────────
def get_image_urls(post):
    files = post["properties"].get("圖片", {}).get("files", [])
    urls = []
    for f in files:
        if f["type"] == "file":
            urls.append(f["file"]["url"])
        elif f["type"] == "external":
            urls.append(f["external"]["url"])
    print(f"取得 {len(urls)} 張圖片")
    return urls

# ── Cloudinary：上傳圖片 ──────────────────────────────
def upload_images(image_urls):
    uploaded = []
    for i, url in enumerate(image_urls):
        result = cloudinary.uploader.upload(url)
        cdn_url = result.get("secure_url")
        if cdn_url:
            print(f"✅ 圖片 {i+1} 上傳成功：{cdn_url}")
            uploaded.append(cdn_url)
        else:
            print(f"❌ 圖片 {i+1} 上傳失敗")
    return uploaded

# ── Gemini：生成文案 ──────────────────────────────────
def generate_caption(topic):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
你是一位專業的 Instagram 文案寫手。
請根據以下主題，寫一篇吸引人的 IG 貼文文案。

主題：{topic}

要求：
- 開場第一句要能讓人停下來看
- 內容有深度，有情緒共鳴
- 結尾加上 2～3 個相關 hashtag
- 總長度控制在 150 字以內
- 用繁體中文撰寫
"""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    caption = response.text.strip()
    print(f"✅ Gemini 文案生成成功")
    return caption

# ── IG：建立輪播容器 ─────────────────────────────────
def create_carousel_item(image_url):
    url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    res = requests.post(url, params={
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": IG_ACCESS_TOKEN
    })
    data = res.json()
    item_id = data.get("id")
    print(f"輪播項目建立：{item_id}")
    return item_id

def create_carousel_container(item_ids, caption):
    url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    res = requests.post(url, params={
        "media_type": "CAROUSEL",
        "children": ",".join(item_ids),
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN
    })
    data = res.json()
    container_id = data.get("id")
    print(f"輪播容器建立：{container_id}")
    return container_id

def publish_carousel(container_id):
    url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    res = requests.post(url, params={
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN
    })
    data = res.json()
    print(f"發布結果：{data}")
    return data.get("id")

# ── Notion：更新狀態 ──────────────────────────────────
def update_status(page_id, status):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    requests.patch(url, headers=headers, json={
        "properties": {
            "狀態": { "status": { "name": status } }
        }
    })
    print(f"✅ Notion 狀態更新為：{status}")

def update_caption(page_id, caption):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    requests.patch(url, headers=headers, json={
        "properties": {
            "文案": {
                "rich_text": [{ "text": { "content": caption } }]
            }
        }
    })
    print(f"✅ 文案已寫回 Notion")

# ── Telegram 通知 ─────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

# ── 主流程 ────────────────────────────────────────────
def main():
    post = get_pending_post()
    if not post:
        print("沒有待發項目，結束")
        return

    page_id = post["id"]
    topic = post["properties"]["主題"]["title"][0]["plain_text"]
    print(f"主題：{topic}")

    # 取得並上傳圖片
    image_urls = get_image_urls(post)
    if not image_urls:
        send_telegram(f"❌ IG 發文失敗！\n原因：Notion 沒有圖片\n主題：{topic}")
        update_status(page_id, "失敗")
        return

    cdn_urls = upload_images(image_urls)
    if not cdn_urls:
        send_telegram(f"❌ IG 發文失敗！\n原因：圖片上傳 Cloudinary 失敗\n主題：{topic}")
        update_status(page_id, "失敗")
        return

    # Gemini 生成文案
    caption = generate_caption(topic)
    update_caption(page_id, caption)

    # 建立輪播並發文
    print("⏳ 建立輪播項目...")
    item_ids = []
    for cdn_url in cdn_urls:
        item_id = create_carousel_item(cdn_url)
        if item_id:
            item_ids.append(item_id)
        time.sleep(2)

    if len(item_ids) < 2:
        send_telegram(f"❌ IG 發文失敗！\n原因：輪播項目建立失敗\n主題：{topic}")
        update_status(page_id, "失敗")
        return

    container_id = create_carousel_container(item_ids, caption)
    if not container_id:
        send_telegram(f"❌ IG 發文失敗！\n原因：輪播容器建立失敗\n主題：{topic}")
        update_status(page_id, "失敗")
        return

    print("⏳ 等待容器準備（30秒）...")
    time.sleep(30)

    post_id = publish_carousel(container_id)
    if post_id:
        update_status(page_id, "已發")
        send_telegram(f"✅ IG 輪播發文成功！\n主題：{topic}\n文案：{caption[:50]}...")
        print("✅ 全部完成！")
    else:
        update_status(page_id, "失敗")
        send_telegram(f"❌ IG 發文失敗！\n原因：發布失敗\n主題：{topic}")

if __name__ == "__main__":
    main()
