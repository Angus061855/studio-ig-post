import { Client } from '@notionhq/client';

const notion = new Client({ auth: process.env.NOTION_TOKEN });

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const { imageUrls, caption, fileNames } = req.body;  // ← 新增 fileNames

    if (!imageUrls || imageUrls.length === 0) {
      return res.status(400).json({ error: '沒有圖片 URL' });
    }

    await notion.pages.create({
      parent: { database_id: process.env.NOTION_DATABASE_ID },
      properties: {
        文案: {
          title: [{ text: { content: caption || '新貼文' } }]
        },
        圖片: {
          files: imageUrls.map((url, i) => ({
            name: fileNames?.[i] || `image-${i + 1}.jpg`,  // ← 用原始檔名
            external: { url }
          }))
        },
        狀態: {
          status: { name: '待發' }   // ← select 改成 status
        }
      }
    });

    return res.status(200).json({ success: true });

  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: err.message });
  }
}

export const config = {
  api: { bodyParser: true }
};
