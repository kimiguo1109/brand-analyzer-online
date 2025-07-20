// 使用内存存储（与upload.js共享）
global.analysisCache = global.analysisCache || new Map();

// 从内存加载任务
function loadTaskFromMemory(taskId) {
  try {
    const task = global.analysisCache.get(taskId);
    return task ? JSON.parse(JSON.stringify(task)) : null; // 深拷贝
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

  const task = loadTaskFromMemory(task_id);

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
