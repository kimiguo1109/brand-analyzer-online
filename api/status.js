import { promises as fs } from 'fs';

// 从文件系统加载任务
async function loadTaskFromFile(taskId) {
  try {
    const taskPath = `/tmp/task_${taskId}.json`;
    const content = await fs.readFile(taskPath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.log(`Task file not found for task ID: ${taskId}. This may be due to server restart or file cleanup.`);
      return null;
    }
    console.error('Failed to load task:', error);
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

  // 首先检查任务是否存在
  const exists = await taskExists(task_id);
  if (!exists) {
    return res.status(404).json({ 
      error: 'Task not found or expired',
      message: '分析任务已过期或被清理，请重新上传文件',
      code: 'TASK_NOT_FOUND',
      suggestion: '这可能是因为服务器重启或任务文件被自动清理。请重新上传文件开始新的分析。'
    });
  }

  // 从文件系统获取任务状态
  const task = await loadTaskFromFile(task_id);

  if (!task) {
    return res.status(404).json({ 
      error: 'Task data corrupted',
      message: '任务数据损坏，请重新上传文件',
      code: 'TASK_CORRUPTED',
      suggestion: '任务文件存在但无法读取。请重新开始分析。'
    });
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
