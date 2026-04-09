import os
import time
import requests
import cloudinary
import cloudinary.uploader

# ── 環境變數 ──────────────────────────────────────────
NOTION_TOKEN          = os.environ["NOTION_API_KEY"]
DATABASE_ID           = os.environ["NOTION_DATABASE_ID_IG"]
IG_USER_ID            = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN       = os.environ["IG_ACCESS_TOKEN"]
CLOUDINARY_CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
CLOUDINARY_API_KEY    = os.environ["CLOUDINARY_API_KEY"]
CLOUDINARY_API_SECRET = os.environ["CLOUDINARY_API_SECRET"]
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

# ── Notion：取得文案 ──────────────────────────────────
def get_caption(post):
    title = post["properties"].get("文案", {}).get("title", [])
    if title:
        return title[0]["plain_text"]
    return ""

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

# ── IG：建立輪播容器 ──────────────────────────────────
def create_carousel_item(image_url):
    url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    res = requests.post(url, params={
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": IG_ACCESS_TOKEN
    })
    data = res.json()
    print(f"IG 回應：{data}")  # 加這行
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

    # 取得文案
    caption = get_caption(post)
    if not caption:
        send_telegram("❌ IG asent061855 發文失敗！\n原因：Notion 沒有填文案")
        update_status(page_id, "失敗")
        return
    print(f"文案：{caption[:30]}...")

    # 取得並上傳圖片
    image_urls = get_image_urls(post)
    if not image_urls:
        send_telegram("❌ IG asent061855 發文失敗！\n原因：Notion 沒有圖片")
        update_status(page_id, "失敗")
        return

    cdn_urls = upload_images(image_urls)
    if not cdn_urls:
        send_telegram("❌ IG asent061855 發文失敗！\n原因：圖片上傳 Cloudinary 失敗")
        update_status(page_id, "失敗")
        return

    # 建立輪播
    print("⏳ 建立輪播項目...")
    item_ids = []
    for cdn_url in cdn_urls:
        item_id = create_carousel_item(cdn_url)
        if item_id:
            item_ids.append(item_id)
        time.sleep(2)

    if len(item_ids) < 2:
        send_telegram("❌ IG asent061855 發文失敗！\n原因：輪播項目建立失敗（至少需要2張圖）")
        update_status(page_id, "失敗")
        return

    container_id = create_carousel_container(item_ids, caption)
    if not container_id:
        send_telegram("❌ IG asent061855 發文失敗！\n原因：輪播容器建立失敗")
        update_status(page_id, "失敗")
        return

    print("⏳ 等待容器準備（30秒）...")
    time.sleep(30)

    post_id = publish_carousel(container_id)
    if post_id:
        update_status(page_id, "已發")
        send_telegram(f"✅ IG asent061855 輪播發文成功！\n文案：{caption[:10]}...")
        print("✅ 全部完成！")
    else:
        update_status(page_id, "失敗")
        send_telegram("❌ IG asent061855 發文失敗！\n原因：發布失敗")

if __name__ == "__main__":
    main()
