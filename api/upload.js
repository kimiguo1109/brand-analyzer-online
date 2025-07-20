import formidable from 'formidable';
import { promises as fs } from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import Papa from 'papaparse';
import BrandAnalyzer from './brand-analyzer.js';

// 全局内存存储任务状态
global.tasks = global.tasks || new Map();

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

    // 生成任务ID
    const taskId = uuidv4();
    
    // 读取文件内容
    const fileContent = await fs.readFile(file.filepath, 'utf-8');
    
    // 创建任务记录
    const task = {
      id: taskId,
      status: 'processing',
      filename: file.originalFilename,
      fileType: ext,
      createdAt: new Date().toISOString(),
      lastUpdated: new Date().toISOString(),
      logs: [
        '📁 文件上传成功', 
        '🚀 启动真正的品牌分析系统',
        '🤖 集成 Gemini AI + TikHub API',
        '⚡ 开始解析文件...'
      ],
      progress: 0,
      results: null,
      error: null,
      processedCount: 0,
      totalCount: 0
    };

    // 保存任务到内存
    saveTaskToMemory(taskId, task);

    // 清理临时文件
    try {
      await fs.unlink(file.filepath);
    } catch (error) {
      console.warn('Failed to cleanup temp file:', error);
    }

    // 异步处理文件，立即返回任务ID
    processFileAsync(taskId, fileContent, ext);

    res.status(200).json({
      task_id: taskId,
      status: 'processing',
      message: '文件上传成功，正在使用Gemini + TikHub进行真实品牌分析...'
    });

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: '文件上传失败: ' + error.message });
  }
}

// 异步处理文件
async function processFileAsync(taskId, fileContent, fileType) {
  const task = loadTaskFromMemory(taskId);
  if (!task) {
    console.error(`Task ${taskId} not found in memory`);
    return;
  }

  try {
    // 更新状态
    task.logs.push('📊 解析文件数据...');
    saveTaskToMemory(taskId, task);

    // 解析文件内容
    let creatorsData = [];
    
    if (fileType === '.csv') {
      creatorsData = await parseCSV(fileContent);
      task.logs.push(`📋 CSV文件解析完成，发现 ${creatorsData.length} 行数据`);
    } else {
      creatorsData = JSON.parse(fileContent);
      task.logs.push(`📋 JSON文件解析完成，发现 ${creatorsData.length} 个数据项`);
    }

    // 提取唯一创作者
    const uniqueCreators = extractUniqueCreators(creatorsData, fileType);
    task.totalCount = uniqueCreators.length;
    task.logs.push(`👥 提取到 ${uniqueCreators.length} 个唯一创作者`);
    task.logs.push('🎯 开始真实分析流程:');
    task.logs.push('   • 🤖 Gemini AI 创作者类型分析');
    task.logs.push('   • 📱 TikHub API 获取用户数据');
    task.logs.push('   • 📊 视频指标计算');
    task.logs.push('   • 🏷️ 品牌关联分析');
    saveTaskToMemory(taskId, task);

    // 初始化品牌分析器
    console.log(`🚀 [${taskId}] 初始化品牌分析器`);
    const analyzer = new BrandAnalyzer();
    const results = [];
    const batchSize = 3; // 减少批次大小，避免API限制

    // 分批处理创作者
    for (let i = 0; i < uniqueCreators.length; i += batchSize) {
      const batch = uniqueCreators.slice(i, i + batchSize);
      const batchNum = Math.floor(i/batchSize) + 1;
      const totalBatches = Math.ceil(uniqueCreators.length/batchSize);
      
      task.logs.push(`🔄 处理批次 ${batchNum}/${totalBatches} (${batch.length} 个创作者)`);
      saveTaskToMemory(taskId, task);

      console.log(`📦 [${taskId}] 处理批次 ${batchNum}/${totalBatches}`);

      // 并发处理批次内的创作者
      const batchPromises = batch.map(async (creator, index) => {
        try {
          console.log(`🔍 [${taskId}] 分析创作者: ${creator.author_unique_id}`);
          const result = await analyzer.analyzeCreator(creator);
          
          task.processedCount++;
          task.progress = Math.floor((task.processedCount / task.totalCount) * 100);
          
          // 更新日志
          const accountType = result.account_type;
          const brandInfo = result.brand ? ` - 品牌: ${result.brand}` : '';
          const confidence = result.brand_confidence ? ` (置信度: ${(result.brand_confidence * 100).toFixed(0)}%)` : '';
          
          task.logs.push(`✅ ${result.author_unique_id}: ${accountType}${brandInfo}${confidence}`);
          saveTaskToMemory(taskId, task);
          
          console.log(`✅ [${taskId}] 完成: ${result.author_unique_id} - ${accountType}`);
          return result;
        } catch (error) {
          console.error(`❌ [${taskId}] 分析创作者失败 ${creator.author_unique_id}:`, error);
          task.logs.push(`❌ ${creator.author_unique_id}: 分析失败 - ${error.message}`);
          saveTaskToMemory(taskId, task);
          return null;
        }
      });

      const batchResults = await Promise.all(batchPromises);
      const validResults = batchResults.filter(r => r !== null);
      results.push(...validResults);

      console.log(`📊 [${taskId}] 批次 ${batchNum} 完成，成功: ${validResults.length}/${batch.length}`);

      // 批次间延迟，避免API限制
      if (i + batchSize < uniqueCreators.length) {
        task.logs.push('⏳ API调用间隔（避免限制）...');
        saveTaskToMemory(taskId, task);
        await new Promise(resolve => setTimeout(resolve, 3000)); // 增加延迟
      }
    }

    console.log(`🎯 [${taskId}] 所有批次处理完成，总结果: ${results.length}`);

    // 统计结果 - 更严格的品牌相关判断
    const brandRelated = results.filter(r => {
      // 官方账号和矩阵账号肯定是品牌相关
      if (r.account_type === 'official account' || r.account_type === 'matrix account') {
        return true;
      }
      
      // UGC创作者：需要有有效的品牌名称且分析详情不能明确说无品牌合作
      if (r.account_type === 'ugc creator') {
        // 检查是否有有效品牌名称
        const hasValidBrand = r.brand && r.brand.trim() && r.brand !== '';
        
        // 检查分析详情是否明确说没有品牌合作
        const analysisDetails = (r.analysis_details || '').toLowerCase();
        const noPartnership = [
          'no indication of a brand partnership',
          'no clear brand partnership',
          'no significant brand indicators',
          'regular creator'
        ].some(indicator => analysisDetails.includes(indicator));
        
        return hasValidBrand && !noPartnership;
      }
      
      return false;
    });
    
    const nonBrand = results.filter(r => !brandRelated.includes(r));

    // 详细统计
    const officialBrands = results.filter(r => r.account_type === 'official account');
    const matrixAccounts = results.filter(r => r.account_type === 'matrix account');
    const ugcCreators = results.filter(r => r.account_type === 'ugc creator');
    const nonBrandedCreators = results.filter(r => r.account_type === 'non-branded creator');

    // 品牌分布统计
    const brandDistribution = {};
    brandRelated.forEach(r => {
      if (r.brand) {
        if (!brandDistribution[r.brand]) {
          brandDistribution[r.brand] = { official: 0, matrix: 0, ugc: 0 };
        }
        if (r.account_type === 'official account') {
          brandDistribution[r.brand].official++;
        } else if (r.account_type === 'matrix account') {
          brandDistribution[r.brand].matrix++;
        } else {
          brandDistribution[r.brand].ugc++;
        }
      }
    });

    // 完成分析
    task.status = 'completed';
    task.progress = 100;
    task.results = {
      total_processed: results.length,
      brand_related_count: brandRelated.length,
      non_brand_count: nonBrand.length,
      
      // 详细分类统计
      official_brand_count: officialBrands.length,
      matrix_account_count: matrixAccounts.length,
      ugc_creator_count: ugcCreators.length,
      non_branded_creator_count: nonBrandedCreators.length,
      
      // 品牌分布
      brand_distribution: brandDistribution,
      unique_brands_count: Object.keys(brandDistribution).length,
      
      // 数据
      brand_related_data: brandRelated,
      non_brand_data: nonBrand,
      all_data: results
    };

    // 成功日志
    task.logs.push('');
    task.logs.push('🎉 ===== 分析完成！=====');
    task.logs.push(`📊 总计处理: ${results.length} 个创作者`);
    task.logs.push(`🏢 品牌相关: ${brandRelated.length} (${((brandRelated.length/results.length)*100).toFixed(1)}%)`);
    task.logs.push(`👤 非品牌: ${nonBrand.length} (${((nonBrand.length/results.length)*100).toFixed(1)}%)`);
    task.logs.push('');
    task.logs.push('📈 ===== 详细分类统计 =====');
    task.logs.push(`🏛️ 官方品牌账号: ${officialBrands.length}`);
    task.logs.push(`🔗 矩阵账号: ${matrixAccounts.length}`);
    task.logs.push(`🎬 UGC创作者: ${ugcCreators.length}`);
    task.logs.push(`👥 非品牌创作者: ${nonBrandedCreators.length}`);
    
    if (Object.keys(brandDistribution).length > 0) {
      task.logs.push('');
      task.logs.push(`🏷️ ===== 发现 ${Object.keys(brandDistribution).length} 个品牌 =====`);
      Object.entries(brandDistribution)
        .sort(([,a], [,b]) => (b.official + b.matrix + b.ugc) - (a.official + a.matrix + a.ugc))
        .forEach(([brand, counts]) => {
          const total = counts.official + counts.matrix + counts.ugc;
          task.logs.push(`   🏷️ ${brand}: ${total} 个账号 (官方:${counts.official}, 矩阵:${counts.matrix}, UGC:${counts.ugc})`);
        });
    }

    task.logs.push('');
    task.logs.push('✨ 使用了真实的API数据：');
    task.logs.push('   • Gemini AI 智能分析创作者类型');
    task.logs.push('   • TikHub API 获取真实用户数据');
    task.logs.push('   • 真实视频指标计算');
    task.logs.push('   • 智能品牌关联判断');

    saveTaskToMemory(taskId, task);
    console.log(`✅ [${taskId}] 任务完成: 处理了 ${results.length} 个创作者`);

  } catch (error) {
    console.error(`❌ [${taskId}] Processing error:`, error);
    task.status = 'error';
    task.error = error.message;
    task.logs.push(`❌ 处理出错: ${error.message}`);
    if (error.stack) {
      task.logs.push(`   详细错误: ${error.stack.split('\n')[0]}`);
    }
    saveTaskToMemory(taskId, task);
  }
}

// 解析CSV文件
function parseCSV(csvContent) {
  return new Promise((resolve, reject) => {
    Papa.parse(csvContent, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors.length > 0) {
          console.warn('CSV parsing warnings:', results.errors);
        }
        resolve(results.data);
      },
      error: (error) => {
        reject(new Error(`CSV解析失败: ${error.message}`));
      }
    });
  });
}

// 提取唯一创作者
function extractUniqueCreators(data, fileType) {
  const uniqueCreatorsMap = new Map();

  data.forEach(item => {
    let creatorInfo;
    
    if (fileType === '.csv') {
      // CSV格式 - 支持多种字段名
      const uniqueId = item.user_unique_id || item.author_unique_id || item.unique_id || item.username;
      if (uniqueId && uniqueId !== 'None' && uniqueId.trim()) {
        creatorInfo = {
          author_unique_id: uniqueId.trim(),
          author_nickname: item.user_nickname || item.author_nickname || item.nickname || '',
          video_id: item.video_id || '',
          title: item.title || '',
          create_time: item.create_time || item.date || item.timestamp || '',
          signature: item.signature || item.bio || item.description || ''
        };
      }
    } else {
      // JSON格式
      if (item.basic_info?.author_unique_id) {
        // 嵌套格式
        const uniqueId = item.basic_info.author_unique_id;
        if (uniqueId && uniqueId !== 'None' && uniqueId.trim()) {
          creatorInfo = {
            author_unique_id: uniqueId.trim(),
            author_nickname: item.basic_info.author_nickname || '',
            video_id: item.video_id || '',
            title: item.title || '',
            create_time: item.basic_info.create_time || '',
            signature: item.description || item.signature || ''
          };
        }
      } else if (item.author_unique_id) {
        // 扁平格式
        const uniqueId = item.author_unique_id;
        if (uniqueId && uniqueId !== 'None' && uniqueId.trim()) {
          creatorInfo = {
            author_unique_id: uniqueId.trim(),
            author_nickname: item.author_nickname || '',
            video_id: item.video_id || '',
            title: item.title || '',
            create_time: item.create_time || '',
            signature: item.signature || ''
          };
        }
      }
    }

    if (creatorInfo && creatorInfo.author_unique_id) {
      uniqueCreatorsMap.set(creatorInfo.author_unique_id, creatorInfo);
    }
  });

  return Array.from(uniqueCreatorsMap.values());
}

// 保存任务到内存
function saveTaskToMemory(taskId, task) {
  try {
    task.lastUpdated = new Date().toISOString();
    global.tasks.set(taskId, JSON.parse(JSON.stringify(task)));
  } catch (error) {
    console.error('Failed to save task to memory:', error);
  }
}

// 从内存加载任务
function loadTaskFromMemory(taskId) {
  try {
    const task = global.tasks.get(taskId);
    if (task) {
      return JSON.parse(JSON.stringify(task));
    }
    return null;
  } catch (error) {
    console.error('Failed to load task from memory:', error);
    return null;
  }
} 