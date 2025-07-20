import { promises as fs } from 'fs';

export default async function handler(req, res) {
  try {
    // 检查临时目录状态
    let tempDirStatus = 'ok';
    let taskFileCount = 0;
    
    try {
      const files = await fs.readdir('/tmp');
      const taskFiles = files.filter(file => file.startsWith('task_') && file.endsWith('.json'));
      taskFileCount = taskFiles.length;
    } catch (error) {
      tempDirStatus = 'error';
    }

    res.status(200).json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      version: '1.0.0',
      system: {
        temp_directory: tempDirStatus,
        active_task_files: taskFileCount,
        node_env: process.env.NODE_ENV || 'development'
      },
      note: '任务文件存储在临时目录中，服务器重启后会丢失'
    });
  } catch (error) {
    res.status(500).json({
      status: 'error',
      timestamp: new Date().toISOString(),
      error: error.message
    });
  }
}
