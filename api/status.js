// 使用内存存储（与upload.js共享）
global.analysisCache = global.analysisCache || new Map();

import { promises as fs } from 'fs';
import path from 'path';

// 检查是否在无服务器环境中
const isServerlessEnvironment = () => {
  return process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME || process.env.NETLIFY;
};

// 从文件系统恢复任务
async function recoverTaskFromFile(taskId) {
  // 在无服务器环境中跳过文件恢复
  if (isServerlessEnvironment()) {
    console.log(`[Status] 跳过文件恢复 ${taskId} - 无服务器环境`);
    return null;
  }
  
  try {
    const taskPath = path.join('/tmp/tasks', `${taskId}.json`);
    const taskData = await fs.readFile(taskPath, 'utf-8');
    const task = JSON.parse(taskData);
    console.log(`[Status] 从文件恢复任务 ${taskId}`);
    // 将恢复的任务重新加入内存缓存
    global.analysisCache.set(taskId, task);
    return task;
  } catch (error) {
    if (error.code === 'ENOENT') {
      console.log(`[Status] 任务文件不存在 ${taskId} - 这在无服务器环境中是正常的`);
    } else {
      console.error(`[Status] 从文件恢复任务失败 ${taskId}:`, error.message);
    }
    return null;
  }
}

// 从内存加载任务
async function loadTaskFromMemory(taskId) {
  try {
    console.log(`[Status] 查找任务 ${taskId}，当前缓存大小: ${global.analysisCache.size}`);
    console.log(`[Status] 缓存中的任务IDs: ${Array.from(global.analysisCache.keys()).join(', ')}`);
    
    // 输出更详细的缓存状态
    for (const [id, task] of global.analysisCache.entries()) {
      console.log(`[Status] 缓存任务 ${id}: 状态=${task.status}, 进度=${task.progress}%, 创建时间=${task.createdAt}`);
    }
    
    let task = global.analysisCache.get(taskId);
    if (task) {
      console.log(`[Status] 找到任务 ${taskId}，状态: ${task.status}, 进度: ${task.progress}%`);
      return JSON.parse(JSON.stringify(task)); // 深拷贝
    } else {
      console.log(`[Status] 任务 ${taskId} 不在内存缓存中`);
      
      // 只在非无服务器环境中尝试文件恢复
      if (!isServerlessEnvironment()) {
        console.log(`[Status] 尝试从文件恢复任务 ${taskId}`);
        task = await recoverTaskFromFile(taskId);
        if (task) {
          return JSON.parse(JSON.stringify(task)); // 深拷贝
        }
      } else {
        console.log(`[Status] 无服务器环境 - 跳过文件恢复，任务可能在不同的函数实例中处理`);
      }
      
      console.log(`[Status] 任务 ${taskId} 无法找到或恢复`);
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
  const task = await loadTaskFromMemory(task_id);

  if (!task) {
    // 提供更详细的错误信息
    const cacheKeys = Array.from(global.analysisCache.keys());
    const isServerless = isServerlessEnvironment();
    const cacheInfo = {
      cache_size: global.analysisCache.size,
      existing_tasks: cacheKeys,
      requested_task: task_id,
      environment: isServerless ? 'serverless' : 'server'
    };
    
    console.error(`[Status] 任务查找失败详情:`, cacheInfo);
    
    // 在无服务器环境中提供更友好的错误消息
    const errorMessage = isServerless 
      ? '任务可能在另一个服务器实例中处理，这在无服务器环境中是正常的。请重新上传文件开始新的分析。'
      : '分析任务已过期或被清理，请重新上传文件';
    
    const suggestion = isServerless
      ? '无服务器环境中任务状态不会在函数调用之间持久化。如果任务正在处理中，请稍候片刻后重试，或重新上传文件。'
      : '这可能是因为服务器重启或任务数据被清理。请重新上传文件开始新的分析。';
    
    return res.status(404).json({ 
      error: 'Task not found',
      message: errorMessage,
      code: 'TASK_NOT_FOUND',
      suggestion: suggestion,
      debug_info: {
        message: isServerless ? '无服务器环境任务状态不持久化' : '任务可能在处理过程中丢失',
        cache_size: global.analysisCache.size,
        existing_task_count: cacheKeys.length,
        environment: isServerless ? 'serverless' : 'server',
        serverless_note: isServerless ? '在无服务器环境中，任务状态在函数调用之间不会保持' : null,
        timestamp: new Date().toISOString()
      }
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
