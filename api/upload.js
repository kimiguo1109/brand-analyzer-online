import formidable from 'formidable';
import { promises as fs } from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import Papa from 'papaparse';
import BrandAnalyzer from './brand-analyzer.js';

export const config = {
  api: {
    bodyParser: false,
  },
  maxDuration: 300,
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const form = formidable({
      uploadDir: '/tmp',
      keepExtensions: true,
      maxFileSize: 50 * 1024 * 1024, // 50MB
    });

    const [fields, files] = await form.parse(req);
    const file = Array.isArray(files.file) ? files.file[0] : files.file;

    if (!file) {
      return res.status(400).json({ error: '请上传文件' });
    }

    // 验证文件类型
    const allowedExtensions = ['.json', '.csv'];
    const ext = path.extname(file.originalFilename || '').toLowerCase();
    
    if (!allowedExtensions.includes(ext)) {
      return res.status(400).json({ error: '只支持JSON和CSV文件格式' });
    }

    // 生成唯一分析ID
    const analysisId = uuidv4();
    
    // 读取文件内容
    const fileContent = await fs.readFile(file.filepath, 'utf-8');
    
    // 清理临时文件
    try {
      await fs.unlink(file.filepath);
    } catch (error) {
      console.error('Failed to delete temp file:', error);
    }

    // 创建任务记录（用于进度追踪）
    const task = {
      id: analysisId,
      status: 'processing',
      filename: file.originalFilename,
      fileType: ext,
      createdAt: new Date().toISOString(),
      progress: 0,
      logs: [
        '📁 文件上传成功', 
        '🚀 启动品牌分析系统',
        '🤖 集成 Gemini AI + TikHub API',
        '⚡ 开始解析文件...'
      ],
      processedCount: 0,
      totalCount: 0
    };
    
    // 存储到全局内存（用于短期进度追踪）
    global.analysisCache = global.analysisCache || new Map();
    global.analysisCache.set(analysisId, task);
    
    // 异步开始分析，立即返回任务ID
    console.log(`开始异步分析文件: ${file.originalFilename} (ID: ${analysisId})`);
    performAnalysisAsync(fileContent, ext, analysisId);
    
    // 立即返回任务ID，让前端开始轮询
    res.status(200).json({
      task_id: analysisId,
      status: 'processing',
      message: '文件上传成功，正在进行品牌分析...'
    });

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ 
      error: '分析失败: ' + error.message,
      status: 'error'
    });
  }
}

// 异步执行分析过程（带进度更新）
async function performAnalysisAsync(fileContent, fileType, analysisId) {
  const updateTaskStatus = (updates) => {
    const task = global.analysisCache.get(analysisId);
    if (task) {
      Object.assign(task, updates, { lastUpdated: new Date().toISOString() });
      global.analysisCache.set(analysisId, task);
    }
  };

  try {
    console.log(`[${analysisId}] 开始解析文件数据...`);
    updateTaskStatus({ 
      logs: [...global.analysisCache.get(analysisId).logs, '📊 解析文件数据...'],
      progress: 10 
    });
    
    // 解析文件内容
    let creatorsData = [];
    
    if (fileType === '.csv') {
      creatorsData = await parseCSV(fileContent);
      console.log(`[${analysisId}] CSV文件解析完成，发现 ${creatorsData.length} 行数据`);
      updateTaskStatus({ 
        logs: [...global.analysisCache.get(analysisId).logs, `📋 CSV文件解析完成，发现 ${creatorsData.length} 行数据`],
        progress: 20 
      });
    } else {
      creatorsData = JSON.parse(fileContent);
      console.log(`[${analysisId}] JSON文件解析完成，发现 ${creatorsData.length} 个数据项`);
      updateTaskStatus({ 
        logs: [...global.analysisCache.get(analysisId).logs, `📋 JSON文件解析完成，发现 ${creatorsData.length} 个数据项`],
        progress: 20 
      });
    }

    if (creatorsData.length === 0) {
      throw new Error('文件中没有找到有效的创作者数据');
    }

    // 提取唯一创作者
    const uniqueCreators = extractUniqueCreators(creatorsData);
    console.log(`[${analysisId}] 提取到 ${uniqueCreators.length} 个唯一创作者`);
    updateTaskStatus({ 
      logs: [...global.analysisCache.get(analysisId).logs, `👥 提取到 ${uniqueCreators.length} 个唯一创作者`],
      progress: 30,
      totalCount: uniqueCreators.length
    });

    if (uniqueCreators.length === 0) {
      throw new Error('没有找到有效的创作者信息');
    }

    // 初始化品牌分析器
    const analyzer = new BrandAnalyzer();
    console.log(`[${analysisId}] 开始品牌关联分析...`);
    updateTaskStatus({ 
      logs: [...global.analysisCache.get(analysisId).logs, '🔍 开始品牌关联分析...'],
      progress: 35
    });
    
    // 分析创作者品牌关联（带进度回调）
    const analysisResults = await analyzer.analyzeCreators(uniqueCreators, (progress, message) => {
      console.log(`[${analysisId}] ${message} (${progress}%)`);
      const adjustedProgress = 35 + (progress * 0.6); // 35-95%范围
      updateTaskStatus({ 
        logs: [...global.analysisCache.get(analysisId).logs, `🤖 ${message}`],
        progress: Math.round(adjustedProgress),
        processedCount: Math.round((progress / 100) * uniqueCreators.length)
      });
    });

    console.log(`[${analysisId}] 分析完成!`);
    
    // 更新为完成状态
    const finalResults = {
      results: analysisResults,
      total_processed: uniqueCreators.length
    };
    
    updateTaskStatus({
      status: 'completed',
      progress: 100,
      results: finalResults,
      logs: [...global.analysisCache.get(analysisId).logs, '✅ 分析完成!']
    });
    
    console.log(`✅ [${analysisId}] 任务完成: 处理了 ${uniqueCreators.length} 个创作者`);

  } catch (error) {
    console.error(`[${analysisId}] 分析失败:`, error);
    
    // 更新为错误状态
    updateTaskStatus({
      status: 'error',
      error: error.message,
      logs: [...(global.analysisCache.get(analysisId)?.logs || []), `❌ 分析失败: ${error.message}`]
    });
  }
}

// CSV解析函数
function parseCSV(csvContent) {
  return new Promise((resolve, reject) => {
    Papa.parse(csvContent, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors.length > 0) {
          console.error('CSV parsing errors:', results.errors);
        }
        resolve(results.data);
      },
      error: (error) => {
        reject(new Error('CSV解析失败: ' + error.message));
      }
    });
  });
}

// 提取唯一创作者函数
function extractUniqueCreators(data) {
  const uniqueCreatorsMap = new Map();
  
  for (const item of data) {
    // 尝试不同的字段名来获取创作者信息
    const creatorFields = ['user_unique_id', 'unique_id', 'uniqueId', 'author_unique_id', 'creator_id', 'username', 'author', 'creator'];
    const displayFields = ['user_nickname', 'display_name', 'displayName', 'author_nickname', 'nickname', 'name'];
    
    let uniqueId = null;
    let displayName = null;
    
    // 查找unique_id
    for (const field of creatorFields) {
      if (item[field] && item[field] !== 'None' && item[field] !== '') {
        uniqueId = String(item[field]).trim();
        break;
      }
    }
    
    // 查找display_name
    for (const field of displayFields) {
      if (item[field] && item[field] !== 'None' && item[field] !== '') {
        displayName = String(item[field]).trim();
        break;
      }
    }
    
    if (uniqueId && !uniqueCreatorsMap.has(uniqueId)) {
      uniqueCreatorsMap.set(uniqueId, {
        unique_id: uniqueId,
        display_name: displayName || uniqueId,
        // 包含其他可能有用的字段
        follower_count: item.follower_count || item.followers || 0,
        following_count: item.following_count || item.following || 0,
        video_count: item.video_count || item.videos || 0,
        heart_count: item.heart_count || item.likes || 0,
      });
    }
  }
  
  return Array.from(uniqueCreatorsMap.values());
} 