import { promises as fs } from 'fs';

// 从文件系统加载任务
async function loadTaskFromFile(taskId) {
  try {
    const taskPath = `/tmp/task_${taskId}.json`;
    const content = await fs.readFile(taskPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.log(`Task file not found for logs request, task ID: ${taskId}`);
      return null;
    }
    console.error('Failed to load task for logs:', error);
    return null;
  }
}

// 检查任务文件是否存在
async function taskExists(taskId) {
  try {
    const taskPath = `/tmp/task_${taskId}.json`;
    await fs.access(taskPath);
    return true;
  } catch (error) {
    return false;
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

  // 检查任务是否存在
  const exists = await taskExists(task_id);
  if (!exists) {
    return res.status(404).json({ 
      error: 'Task not found',
      message: '任务已过期或被清理',
      code: 'TASK_NOT_FOUND'
    });
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
