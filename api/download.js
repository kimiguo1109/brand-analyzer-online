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

  const { task_id, file_type } = req.query;

  if (!task_id || !file_type) {
    return res.status(400).json({ error: 'Task ID and file type are required' });
  }

  // 从文件系统获取任务信息
  const task = await loadTaskFromFile(task_id);

  if (!task) {
    return res.status(404).json({ error: 'Task not found' });
  }

  if (task.status !== 'completed') {
    return res.status(400).json({ error: 'Task not completed yet' });
  }

  if (!task.results || !task.results.detailed_results) {
    return res.status(400).json({ error: 'No analysis results available' });
  }

  // 根据类型过滤结果
  const allResults = task.results.detailed_results;
  let filteredResults = [];
  let filename = '';

  if (file_type === 'brand') {
    // 品牌相关：包含官方品牌、矩阵账号、有品牌名的UGC创作者
    filteredResults = allResults.filter(r => 
      r.is_brand || 
      r.is_matrix_account || 
      (r.extracted_brand_name && r.extracted_brand_name.trim())
    );
    filename = 'brand_related_creators.csv';
  } else if (file_type === 'non_brand') {
    // 非品牌：没有品牌关联的创作者
    filteredResults = allResults.filter(r => 
      !r.is_brand && 
      !r.is_matrix_account && 
      (!r.extracted_brand_name || !r.extracted_brand_name.trim())
    );
    filename = 'non_brand_creators.csv';
  } else if (file_type === 'all') {
    // 全部结果
    filteredResults = allResults;
    filename = 'all_creators_analysis.csv';
  } else {
    return res.status(400).json({ error: 'Invalid file type. Use: brand, non_brand, or all' });
  }

  // 生成CSV内容
  const csvContent = generateCSVContent(filteredResults);

  // 设置响应头
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  res.setHeader('Content-Length', Buffer.byteLength(csvContent, 'utf8'));

  res.status(200).send(csvContent);
}

function generateCSVContent(results) {
  // CSV字段定义
  const fieldnames = [
    'video_id',
    'author_unique_id', 
    'author_link',
    'signature',
    'account_type',
    'brand',
    'email',
    'recent_posts_views_avg',
    'recent_posts_like_avg', 
    'recent_posts_share_avg',
    'posting_frequency',
    'stability_score',
    'brand_confidence',
    'analysis_details',
    'author_followers_count',
    'author_followings_count',
    'videoCount',
    'author_avatar',
    'create_times'
  ];

  // 生成CSV头部
  let csvContent = fieldnames.map(field => `"${field}"`).join(',') + '\n';

  // 生成数据行
  results.forEach(result => {
    // 确定账户类型
    let accountType = 'ugc creator';
    if (result.is_brand) {
      accountType = 'official account';
    } else if (result.is_matrix_account) {
      accountType = 'matrix account';
    }

    // 清理和转义数据
    const row = [
      escapeCSVField(result.video_id || ''),
      escapeCSVField(result.author_unique_id || ''),
      escapeCSVField(result.author_link || ''),
      escapeCSVField(result.signature || ''),
      escapeCSVField(accountType),
      escapeCSVField(result.extracted_brand_name || ''),
      escapeCSVField(result.email || ''),
      result.recent_posts_views_avg || 0,
      result.recent_posts_like_avg || 0,
      result.recent_posts_share_avg || 0,
      result.posting_frequency || 0,
      result.stability_score || 0,
      result.brand_confidence || 0,
      escapeCSVField(result.analysis_details || ''),
      result.author_followers_count || 0,
      result.author_followings_count || 0,
      result.videoCount || 0,
      escapeCSVField(result.author_avatar || ''),
      escapeCSVField(result.create_times || '')
    ];

    csvContent += row.join(',') + '\n';
  });

  return csvContent;
}

function escapeCSVField(field) {
  // 转换为字符串并清理
  let value = String(field || '');
  
  // 移除换行符和回车符
  value = value.replace(/[\r\n]/g, ' ');
  
  // 如果包含逗号、引号或换行符，需要用引号包围并转义引号
  if (value.includes(',') || value.includes('"') || value.includes('\n')) {
    value = value.replace(/"/g, '""'); // 转义引号
    value = `"${value}"`; // 用引号包围
  } else {
    value = `"${value}"`; // 统一用引号包围以保持一致性
  }
  
  return value;
}
