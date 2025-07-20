export default function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id } = req.query;

  if (!task_id) {
    return res.status(400).json({ error: 'Task ID is required' });
  }

  // 获取任务状态
  const task = global.analysisTasksCache?.get(task_id);

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
