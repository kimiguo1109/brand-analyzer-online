import { promises as fs } from 'fs';
import path from 'path';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const tmpDir = '/tmp';
    const maxAge = 24 * 60 * 60 * 1000; // 24小时
    const now = Date.now();
    let cleanedCount = 0;

    // 读取 /tmp 目录中的所有文件
    const files = await fs.readdir(tmpDir);
    
    // 过滤出任务文件
    const taskFiles = files.filter(file => file.startsWith('task_') && file.endsWith('.json'));

    for (const file of taskFiles) {
      try {
        const filePath = path.join(tmpDir, file);
        const stats = await fs.stat(filePath);
        
        // 检查文件是否超过24小时
        if (now - stats.mtime.getTime() > maxAge) {
          await fs.unlink(filePath);
          cleanedCount++;
          console.log(`Cleaned up expired task file: ${file}`);
        }
      } catch (error) {
        console.error(`Error processing file ${file}:`, error);
      }
    }

    res.status(200).json({
      message: `清理完成，删除了 ${cleanedCount} 个过期任务文件`,
      cleaned_count: cleanedCount,
      total_task_files: taskFiles.length
    });

  } catch (error) {
    console.error('Cleanup error:', error);
    res.status(500).json({ error: '清理过程中出现错误: ' + error.message });
  }
}
