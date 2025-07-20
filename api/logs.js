import { promises as fs } from 'fs';
import path from 'path';

// 任务状态文件存储路径
const TASKS_DIR = '/tmp/tasks';

// 确保任务目录存在
async function ensureTasksDir() {
  try {
    await fs.mkdir(TASKS_DIR, { recursive: true });
  } catch (error) {
    // 目录可能已存在，忽略错误
  }
}

// 从文件系统加载任务
async function loadTaskFromFile(taskId) {
  try {
    await ensureTasksDir();
    const taskPath = path.join(TASKS_DIR, `${taskId}.json`);
    const taskData = await fs.readFile(taskPath, 'utf-8');
    return JSON.parse(taskData);
  } catch (error) {
    console.error('Failed to load task from file:', error);
    return null;
  }
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id } = req.query;

  if (!task_id) {
    return res.status(400).json({ error: 'Task ID is required' });
  }

  const task = await loadTaskFromFile(task_id);

  if (!task) {
    return res.status(404).json({ 
      error: 'Task data corrupted',
      message: '任务数据无法读取',
      code: 'TASK_CORRUPTED'
    });
  }

  res.status(200).json({
    task_id: task.id,
    logs: task.logs || []
  });
}
