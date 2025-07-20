import { promises as fs } from 'fs';

// 从文件系统加载任务
async function loadTaskFromFile(taskId) {
  try {
    const taskPath = `/tmp/task_${taskId}.json`;
    const content = await fs.readFile(taskPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.error('Failed to load task:', error);
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

  // 从文件系统获取任务状态
  const task = await loadTaskFromFile(task_id);

  if (!task) {
    return res.status(404).json({ error: 'Task not found' });
  }

  const response = {
    task_id: task.id,
    status: task.status,
    progress: task.progress || 0,
    created_at: task.createdAt,
    processed_count: task.processedCount || 0,
    total_count: task.totalCount || 0
  };

  // 如果任务完成，包含结果
  if (task.status === 'completed' && task.results) {
    response.results = task.results;
  }

  // 如果有错误，包含错误信息
  if (task.status === 'error' && task.error) {
    response.error = task.error;
  }

  res.status(200).json(response);
}
