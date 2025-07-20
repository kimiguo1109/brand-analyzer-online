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

    // 直接进行分析
    console.log(`开始分析文件: ${file.originalFilename} (ID: ${analysisId})`);
    
    const analysisResult = await performAnalysis(fileContent, ext, analysisId);
    
    // 返回完整的分析结果
    res.status(200).json({
      analysis_id: analysisId,
      filename: file.originalFilename,
      status: 'completed',
      ...analysisResult
    });

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ 
      error: '分析失败: ' + error.message,
      status: 'error'
    });
  }
}

// 执行完整的分析过程
async function performAnalysis(fileContent, fileType, analysisId) {
  try {
    console.log(`[${analysisId}] 开始解析文件数据...`);
    
    // 解析文件内容
    let creatorsData = [];
    
    if (fileType === '.csv') {
      creatorsData = await parseCSV(fileContent);
      console.log(`[${analysisId}] CSV文件解析完成，发现 ${creatorsData.length} 行数据`);
    } else {
      creatorsData = JSON.parse(fileContent);
      console.log(`[${analysisId}] JSON文件解析完成，发现 ${creatorsData.length} 个数据项`);
    }

    if (creatorsData.length === 0) {
      throw new Error('文件中没有找到有效的创作者数据');
    }

    // 提取唯一创作者
    const uniqueCreators = extractUniqueCreators(creatorsData);
    console.log(`[${analysisId}] 提取到 ${uniqueCreators.length} 个唯一创作者`);

    if (uniqueCreators.length === 0) {
      throw new Error('没有找到有效的创作者信息');
    }

    // 初始化品牌分析器
    const analyzer = new BrandAnalyzer();
    console.log(`[${analysisId}] 开始品牌关联分析...`);
    
    // 分析创作者品牌关联
    const analysisResults = await analyzer.analyzeCreators(uniqueCreators, (progress, message) => {
      console.log(`[${analysisId}] ${message} (${progress}%)`);
    });

    console.log(`[${analysisId}] 分析完成!`);
    
    return {
      results: analysisResults,
      total_processed: uniqueCreators.length,
      analysis_logs: [
        '📁 文件上传成功', 
        '🚀 启动真正的品牌分析系统',
        '🤖 集成 Gemini AI + TikHub API',
        `📋 解析完成，发现 ${uniqueCreators.length} 个唯一创作者`,
        '🔍 开始品牌关联分析...',
        '✅ 分析完成!'
      ]
    };

  } catch (error) {
    console.error(`[${analysisId}] 分析失败:`, error);
    throw error;
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
    const creatorFields = ['unique_id', 'uniqueId', 'creator_id', 'username', 'author', 'creator'];
    const displayFields = ['display_name', 'displayName', 'nickname', 'name'];
    
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