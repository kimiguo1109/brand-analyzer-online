// 使用内存存储，确保访问全局任务存储
global.tasks = global.tasks || new Map();

// 从内存加载任务
function loadTaskFromMemory(taskId) {
  try {
    const task = global.tasks.get(taskId);
    if (task) {
      return JSON.parse(JSON.stringify(task)); // 深拷贝
    }
    return null;
  } catch (error) {
    console.error('Failed to load task from memory:', error);
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

  // 从内存获取任务状态
  const task = loadTaskFromMemory(task_id);

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
