export const config = {
  api: {
    bodyParser: false,
  },
  maxDuration: 300,
};

global.analysisTasksCache = global.analysisTasksCache || new Map();

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // 模拟文件上传和处理
    const taskId = Date.now().toString();
    
    const task = {
      id: taskId,
      status: 'processing',
      filename: 'uploaded_file.json',
      createdAt: new Date().toISOString(),
      logs: ['文件上传成功', '开始分析...'],
      progress: 0,
    };

    global.analysisTasksCache.set(taskId, task);

    // 模拟异步处理
    setTimeout(() => {
      const currentTask = global.analysisTasksCache.get(taskId);
      if (currentTask) {
        currentTask.status = 'completed';
        currentTask.progress = 100;
        currentTask.results = {
          total_processed: 397,
          brand_related_count: 346,
          non_brand_count: 51,
          official_account_count: 35,
          matrix_account_count: 50,
          ugc_creator_count: 216
        };
        global.analysisTasksCache.set(taskId, currentTask);
      }
    }, 5000);

    res.status(200).json({
      task_id: taskId,
      status: 'processing',
      message: '文件上传成功，开始处理...'
    });

  } catch (error) {
    res.status(500).json({ error: '文件上传失败: ' + error.message });
  }
}
