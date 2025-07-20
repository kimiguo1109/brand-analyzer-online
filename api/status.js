export default function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id } = req.query;

  if (!task_id) {
    return res.status(400).json({ error: 'Task ID is required' });
  }

  const task = global.analysisTasksCache?.get(task_id);

  if (!task) {
    return res.status(404).json({ error: 'Task not found' });
  }

  const response = {
    task_id: task.id,
    status: task.status,
    progress: task.progress || 0,
    created_at: task.createdAt,
  };

  if (task.status === 'completed' && task.results) {
    response.results = task.results;
  }

  res.status(200).json(response);
}
