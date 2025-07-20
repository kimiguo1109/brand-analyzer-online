// 使用内存存储（与upload.js共享）
global.analysisCache = global.analysisCache || new Map();

// 从内存加载任务
function loadTaskFromMemory(taskId) {
  try {
    console.log(`[Status] 查找任务 ${taskId}，当前缓存大小: ${global.analysisCache.size}`);
    console.log(`[Status] 缓存中的任务IDs: ${Array.from(global.analysisCache.keys()).join(', ')}`);
    
    const task = global.analysisCache.get(taskId);
    if (task) {
      console.log(`[Status] 找到任务 ${taskId}，状态: ${task.status}`);
      return JSON.parse(JSON.stringify(task)); // 深拷贝
    } else {
      console.log(`[Status] 任务 ${taskId} 不在缓存中`);
      return null;
    }
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
      error: 'Task not found or expired',
      message: '分析任务已过期或被清理，请重新上传文件',
      code: 'TASK_NOT_FOUND',
      suggestion: '这可能是因为服务器重启或任务数据被清理。请重新上传文件开始新的分析。'
    });
  }

  const response = {
    task_id: task.id,
    status: task.status,
    progress: task.progress || 0,
    created_at: task.createdAt,
    processed_count: task.processedCount || 0,
    total_count: task.totalCount || 0,
    logs: task.logs || [] // 直接包含日志信息
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
