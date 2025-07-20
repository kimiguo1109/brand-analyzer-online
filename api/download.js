import { promises as fs } from 'fs';

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

  const { task_id, file_type } = req.query;

  if (!task_id || !file_type) {
    return res.status(400).json({ error: 'Task ID and file type are required' });
  }

  // 从内存获取任务信息
  const task = loadTaskFromMemory(task_id);

  if (!task) {
    return res.status(404).json({ 
      error: 'Task data corrupted',
      message: '任务数据损坏，无法下载文件',
      code: 'TASK_CORRUPTED'
    });
  }

  if (task.status !== 'completed') {
    return res.status(400).json({ 
      error: 'Task not completed yet',
      message: '分析尚未完成，请等待分析完成后再下载',
      current_status: task.status
    });
  }

  if (!task.results || !task.results.detailed_results) {
    return res.status(400).json({ 
      error: 'No analysis results available',
      message: '没有可用的分析结果',
      code: 'NO_RESULTS'
    });
  }

  // 根据类型过滤结果
  const allResults = task.results.detailed_results;
  let filteredResults = [];
  let filename = '';

  if (file_type === 'brand_related' || file_type === 'brand') {
    // 品牌相关：包含所有品牌相关的创作者
    filteredResults = allResults.filter(r => r.is_brand);
    filename = 'brand_related_creators.csv';
  } else if (file_type === 'non_brand') {
    // 非品牌：没有品牌关联的创作者
    filteredResults = allResults.filter(r => !r.is_brand);
    filename = 'non_brand_creators.csv';
  } else if (file_type === 'all') {
    // 全部结果
    filteredResults = allResults;
    filename = 'all_creators_analysis.csv';
  } else {
    return res.status(400).json({ error: 'Invalid file type. Use: brand_related, non_brand, or all' });
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
    'author_unique_id', 
    'signature',
    'is_brand',
    'brand_name',
    'author_followers_count',
    'account_type',
    'confidence_score'
  ];

  // 生成CSV头部
  let csvContent = fieldnames.map(field => `"${field}"`).join(',') + '\n';

  // 生成数据行
  results.forEach(result => {
    // 清理和转义数据
    const row = [
      escapeCSVField(result.author_unique_id || ''),
      escapeCSVField(result.signature || ''),
      result.is_brand ? 'true' : 'false',
      escapeCSVField(result.brand_name || ''),
      result.author_followers_count || 0,
      escapeCSVField(result.account_type || 'ugc_creator'),
      result.confidence_score || 0
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
