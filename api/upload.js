import { v2 as cloudinary } from 'cloudinary';
import { Client } from '@notionhq/client';
import formidable from 'formidable';
import fs from 'fs';

export const config = {
  api: {
    bodyParser: false,
  },
};

cloudinary.config({
  cloud_name: process.env.CLOUDINARY_CLOUD_NAME,
  api_key: process.env.CLOUDINARY_API_KEY,
  api_secret: process.env.CLOUDINARY_API_SECRET,
});

const notion = new Client({ auth: process.env.NOTION_TOKEN });

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const form = formidable({ multiples: true });

  form.parse(req, async (err, fields, files) => {
    if (err) {
      return res.status(500).json({ error: '解析失敗' });
    }

    try {
      const caption = fields.caption?.[0] || fields.caption || '';
      const hashtags = fields.hashtags?.[0] || fields.hashtags || '';
      const scheduleDate = fields.scheduleDate?.[0] || fields.scheduleDate || '';

      // 上傳圖片到 Cloudinary
      const imageFiles = Array.isArray(files.images) ? files.images : [files.images];
      const uploadedUrls = [];

      for (const file of imageFiles) {
        if (!file) continue;
        const result = await cloudinary.uploader.upload(file.filepath, {
          folder: 'ig-posts',
        });
        uploadedUrls.push(result.secure_url);
      }

      // 寫入 Notion
      await notion.pages.create({
        parent: { database_id: process.env.NOTION_DATABASE_ID },
        properties: {
          '名稱': {
            title: [{ text: { content: caption.substring(0, 50) || '新貼文' } }],
          },
          '文案': {
            rich_text: [{ text: { content: caption } }],
          },
          'Hashtags': {
            rich_text: [{ text: { content: hashtags } }],
          },
          '預計發布時間': {
            date: scheduleDate ? { start: scheduleDate } : null,
          },
          '圖片網址': {
            url: uploadedUrls[0] || null,
          },
          '狀態': {
            select: { name: '待發布' },
          },
        },
      });

      return res.status(200).json({
        success: true,
        message: '上傳成功！',
        images: uploadedUrls,
      });

    } catch (error) {
      console.error(error);
      return res.status(500).json({ error: '上傳失敗：' + error.message });
    }
  });
}
