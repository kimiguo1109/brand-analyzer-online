import formidable from 'formidable';
import { promises as fs } from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import Papa from 'papaparse';
import BrandAnalyzer from './brand-analyzer.js';

// 检查是否在无服务器环境中
const isServerlessEnvironment = () => {
  return process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME || process.env.NETLIFY;
};

// 确保任务目录存在
async function ensureTasksDir() {
  if (isServerlessEnvironment()) {
    console.log('[Persist] 跳过目录创建 - 无服务器环境');
    return;
  }
  
  try {
    await fs.mkdir('/tmp/tasks', { recursive: true });
  } catch (error) {
    // 目录可能已存在，忽略错误
  }
}

// 持久化任务到文件系统
async function persistTask(taskId, task) {
  if (isServerlessEnvironment()) {
    console.log(`[Persist] 跳过文件持久化 ${taskId} - 无服务器环境`);
    return;
  }
  
  try {
    await ensureTasksDir();
    const taskPath = path.join('/tmp/tasks', `${taskId}.json`);
    await fs.writeFile(taskPath, JSON.stringify(task, null, 2));
    console.log(`[Persist] 任务 ${taskId} 已保存到文件`);
  } catch (error) {
    console.error(`[Persist] 保存任务失败 ${taskId}:`, error);
  }
}

// 从文件系统恢复任务
async function recoverTask(taskId) {
  if (isServerlessEnvironment()) {
    console.log(`[Recover] 跳过文件恢复 ${taskId} - 无服务器环境`);
    return null;
  }
  
  try {
    const taskPath = path.join('/tmp/tasks', `${taskId}.json`);
    const taskData = await fs.readFile(taskPath, 'utf-8');
    const task = JSON.parse(taskData);
    console.log(`[Recover] 从文件恢复任务 ${taskId}`);
    return task;
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.log(`[Recover] 任务文件不存在 ${taskId} - 这在无服务器环境中是正常的`);
    } else {
      console.error(`[Recover] 恢复任务失败 ${taskId}:`, error.message);
    }
    return null;
  }
}

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

        console.log(`开始分析文件: ${file.originalFilename} (ID: ${analysisId})`);
    
    // 预处理：检查文件大小决定处理策略  
    let creatorsData = [];
    if (ext === '.csv') {
      creatorsData = await parseCSV(fileContent);
    } else {
      creatorsData = JSON.parse(fileContent);
    }
    
    const uniqueCreators = extractUniqueCreators(creatorsData);
    console.log(`提取到 ${uniqueCreators.length} 个创作者`);
    
    // 小文件直接同步处理，大文件异步处理  
    if (uniqueCreators.length <= 15) {
      console.log(`📦 小文件模式: ${uniqueCreators.length} 个创作者，直接同步分析`);
      
      try {
        const analysisResult = await performSyncAnalysis(uniqueCreators, analysisId);
        
        // 直接返回完整结果
        res.status(200).json({
          task_id: analysisId,
          status: 'completed',
          filename: file.originalFilename,
          ...analysisResult
        });
      } catch (error) {
        console.error(`同步分析失败:`, error);
        res.status(500).json({
          error: '分析失败: ' + error.message,
          status: 'error'
        });
      }
      
    } else {
      console.log(`📊 大文件模式: ${uniqueCreators.length} 个创作者，异步处理`);
      
      // 创建任务记录
      const task = {
        id: analysisId,
        status: 'processing',
        filename: file.originalFilename,
        createdAt: new Date().toISOString(),
        progress: 0,
        logs: [
          '📁 文件上传成功', 
          '🚀 启动品牌分析系统',
          `👥 发现 ${uniqueCreators.length} 个创作者`,
          '🤖 开始智能品牌分析...'
        ],
        processedCount: 0,
        totalCount: uniqueCreators.length
      };
      
      // 存储到全局内存
      global.analysisCache = global.analysisCache || new Map();
      global.analysisCache.set(analysisId, task);
      console.log(`[Upload] 创建任务 ${analysisId}，缓存大小: ${global.analysisCache.size}`);
      
      // 持久化任务到文件系统（仅在非无服务器环境中）
      await persistTask(analysisId, task);
      
      // 异步处理
      performAsyncAnalysis(uniqueCreators, analysisId);
      
      // 立即返回任务ID
      res.status(200).json({
        task_id: analysisId,
        status: 'processing',
        message: `文件上传成功，正在分析 ${uniqueCreators.length} 个创作者...`,
        total_count: uniqueCreators.length
      });
    }

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ 
      error: '分析失败: ' + error.message,
      status: 'error'
    });
  }
}

// 同步分析（小文件）
async function performSyncAnalysis(uniqueCreators, analysisId) {
  try {
    console.log(`[${analysisId}] 开始同步分析 ${uniqueCreators.length} 个创作者`);
    
    const analyzer = new BrandAnalyzer();
    const analysisResults = await analyzer.analyzeCreators(uniqueCreators, (progress, message) => {
      console.log(`[${analysisId}] ${message} (${progress}%)`);
    });
    
    console.log(`[${analysisId}] 同步分析完成!`);
    
    return {
      results: analysisResults,
      total_processed: uniqueCreators.length,
      analysis_logs: [
        '📁 文件上传成功',
        '🚀 启动品牌分析系统', 
        `👥 提取到 ${uniqueCreators.length} 个创作者`,
        '🤖 智能品牌分析完成',
        '✅ 分析完成!'
      ]
    };
    
  } catch (error) {
    console.error(`[${analysisId}] 同步分析失败:`, error);
    throw error;
  }
}

// 异步分析（大文件，带进度更新）  
async function performAsyncAnalysis(uniqueCreators, analysisId) {
  const updateTaskStatus = async (updates) => {
    try {
      let task = global.analysisCache.get(analysisId);
      if (!task) {
        // 在非无服务器环境中尝试从文件系统恢复
        if (!isServerlessEnvironment()) {
          console.warn(`[Upload] 任务 ${analysisId} 不在缓存中，尝试从文件恢复`);
          task = await recoverTask(analysisId);
        } else {
          console.warn(`[Upload] 任务 ${analysisId} 不在缓存中，无服务器环境跳过文件恢复`);
        }
        
        if (!task) {
          // 如果文件也没有，重新创建基础任务结构
          const environmentNote = isServerlessEnvironment() ? '无服务器环境' : '文件也不存在';
          console.warn(`[Upload] 任务 ${analysisId} ${environmentNote}，重新创建`);
          task = {
            id: analysisId,
            status: 'processing',
            createdAt: new Date().toISOString(),
            progress: 0,
            logs: isServerlessEnvironment() ? ['🔄 无服务器环境任务重建...'] : ['🔄 任务恢复中...'],
            processedCount: 0,
            totalCount: uniqueCreators.length
          };
        }
        global.analysisCache.set(analysisId, task);
      }
      
      // 安全地合并更新
      Object.assign(task, updates, { lastUpdated: new Date().toISOString() });
      
      // 安全地合并日志
      if (updates.logs) {
        task.logs = updates.logs;
      }
      
      global.analysisCache.set(analysisId, task);
      
      // 持久化更新到文件系统（仅在非无服务器环境中）
      await persistTask(analysisId, task);
      
      console.log(`[Upload] 更新任务 ${analysisId}，进度: ${updates.progress || task.progress}%，状态: ${updates.status || task.status}`);
    } catch (error) {
      console.error(`[Upload] 更新任务状态失败 ${analysisId}:`, error);
    }
  };

  // 安全地获取当前日志
  const getCurrentLogs = () => {
    try {
      const task = global.analysisCache.get(analysisId);
      return task?.logs || ['🔄 分析开始...'];
    } catch (error) {
      console.error(`[Upload] 获取日志失败:`, error);
      return ['🔄 分析开始...'];
    }
  };

  try {
    console.log(`[${analysisId}] 开始异步分析 ${uniqueCreators.length} 个创作者`);
    await updateTaskStatus({ 
      logs: [...getCurrentLogs(), '🔄 初始化分析引擎...'],
      progress: 10 
    });

    // 初始化品牌分析器
    const analyzer = new BrandAnalyzer();
    await updateTaskStatus({ 
      logs: [...getCurrentLogs(), '🔍 开始智能品牌分析...'],
      progress: 20
    });
    
    // 分析创作者品牌关联（带进度回调）
    const analysisResults = await analyzer.analyzeCreators(uniqueCreators, (progress, message) => {
      try {
        console.log(`[${analysisId}] ${message} (${progress}%)`);
        const adjustedProgress = 20 + (progress * 0.75); // 20-95%范围
        // 进度回调需要异步处理，但不等待结果
        updateTaskStatus({ 
          logs: [...getCurrentLogs(), `🤖 ${message}`],
          progress: Math.round(adjustedProgress),
          processedCount: Math.round((progress / 100) * uniqueCreators.length)
        }).catch(error => {
          console.error(`[${analysisId}] 进度更新失败:`, error);
        });
      } catch (error) {
        console.error(`[${analysisId}] 进度更新失败:`, error);
      }
    });

    console.log(`[${analysisId}] 异步分析完成!`);
    
    // 更新为完成状态
    const finalResults = {
      results: analysisResults,
      total_processed: uniqueCreators.length
    };
    
    await updateTaskStatus({
      status: 'completed',
      progress: 100,
      results: finalResults,
      logs: [...getCurrentLogs(), '🎉 大文件分析完成!', `📊 成功分析了 ${uniqueCreators.length} 个创作者`]
    });
    
    console.log(`✅ [${analysisId}] 异步任务完成: 处理了 ${uniqueCreators.length} 个创作者`);

  } catch (error) {
    console.error(`[${analysisId}] 分析失败:`, error);
    
    // 更新为错误状态
    await updateTaskStatus({
      status: 'error',
      error: error.message,
      logs: [...getCurrentLogs(), `❌ 分析失败: ${error.message}`]
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