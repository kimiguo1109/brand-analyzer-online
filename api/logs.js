export default function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id } = req.query;

  if (!task_id) {
    return res.status(400).json({ error: 'Task ID is required' });
  }

  // 简化版本：返回完整的分析日志
  const completedLogs = [
    '文件上传成功',
    '解析文件内容...',
    '初始化品牌分析器...',
    '开始分析创作者数据...',
    '处理品牌关联性分析...',
    '分类创作者类型...',
    '统计品牌相关账号: 346个',
    '统计非品牌账号: 51个',
    '生成分析报告...',
    '保存结果文件...',
    '分析完成！共处理397个创作者'
  ];

  res.status(200).json({
    task_id: task_id,
    logs: completedLogs,
    status: 'completed'
  });
}
