import formidable from 'formidable';
import { promises as fs } from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

export const config = {
  api: {
    bodyParser: false,
  },
  maxDuration: 300,
};

// 全局任务存储
global.analysisTasksCache = global.analysisTasksCache || new Map();

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
      fileContent: fileContent,
      createdAt: new Date().toISOString(),
      logs: ['文件上传成功', '开始解析文件...'],
      progress: 0,
      results: null,
      error: null,
      processedCount: 0,
      totalCount: 0
    };

    global.analysisTasksCache.set(taskId, task);

    // 清理临时文件
    try {
      await fs.unlink(file.filepath);
    } catch (error) {
      console.warn('Failed to cleanup temp file:', error);
    }

    // 开始异步处理
    processFileAsync(taskId, fileContent, ext);

    res.status(200).json({
      task_id: taskId,
      status: 'processing',
      message: '文件上传成功，开始分析...'
    });

  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: '文件上传失败: ' + error.message });
  }
}

async function processFileAsync(taskId, fileContent, fileType) {
  const task = global.analysisTasksCache.get(taskId);
  if (!task) return;

  try {
    // 解析文件内容
    let creatorsData = [];
    
    if (fileType === '.csv') {
      creatorsData = await parseCSV(fileContent);
    } else if (fileType === '.json') {
      creatorsData = JSON.parse(fileContent);
    }

    task.logs.push(`解析完成，发现 ${creatorsData.length} 个数据项`);
    
    // 提取唯一创作者
    const uniqueCreators = extractUniqueCreators(creatorsData, fileType);
    task.totalCount = uniqueCreators.length;
    task.logs.push(`去重后有 ${uniqueCreators.length} 个唯一创作者`);
    task.progress = 5;
    global.analysisTasksCache.set(taskId, task);

    // 分析每个创作者
    const results = [];
    const batchSize = 5; // 每批处理5个，减少并发压力
    
    for (let i = 0; i < uniqueCreators.length; i += batchSize) {
      const batch = uniqueCreators.slice(i, i + batchSize);
      
      // 并发处理一批创作者
      const batchPromises = batch.map(creator => analyzeCreator(creator, taskId));
      const batchResults = await Promise.allSettled(batchPromises);
      
      // 收集结果
      batchResults.forEach((result, index) => {
        const creator = batch[index];
        task.processedCount++;
        
        if (result.status === 'fulfilled' && result.value) {
          results.push(result.value);
          task.logs.push(`✅ 已分析: ${creator.author_unique_id}`);
        } else {
          task.logs.push(`❌ 分析失败: ${creator.author_unique_id} - ${result.reason?.message || '未知错误'}`);
        }
        
        // 更新进度
        const progress = Math.round((task.processedCount / task.totalCount) * 100);
        task.progress = Math.max(5, Math.min(95, progress));
      });
      
      global.analysisTasksCache.set(taskId, task);
      
      // 批次间延迟，避免API限制
      if (i + batchSize < uniqueCreators.length) {
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    }

    // 分析完成，生成统计结果
    const statistics = generateStatistics(results);
    
    task.status = 'completed';
    task.progress = 100;
    task.results = statistics;
    task.logs.push(`分析完成！共处理 ${results.length} 个创作者`);
    task.logs.push(`品牌相关: ${statistics.brand_related_count}, 非品牌: ${statistics.non_brand_count}`);
    
    global.analysisTasksCache.set(taskId, task);

  } catch (error) {
    console.error('Processing error:', error);
    task.status = 'error';
    task.error = error.message;
    task.logs.push(`处理出错: ${error.message}`);
    global.analysisTasksCache.set(taskId, task);
  }
}

async function parseCSV(csvContent) {
  const lines = csvContent.split('\n').filter(line => line.trim());
  if (lines.length < 2) return [];
  
  const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
  const data = [];
  
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    if (values.length >= headers.length) {
      const row = {};
      headers.forEach((header, index) => {
        row[header] = values[index] || '';
      });
      data.push(row);
    }
  }
  
  return data;
}

function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  
  result.push(current.trim());
  return result;
}

function extractUniqueCreators(data, fileType) {
  const unique = new Map();
  
  data.forEach(item => {
    let uniqueId, nickname, videoId;
    
    if (fileType === '.csv') {
      uniqueId = item.user_unique_id || item.author_unique_id || item.unique_id;
      nickname = item.user_nickname || item.author_nickname || item.nickname;
      videoId = item.video_id || '';
    } else {
      // JSON格式
      const basicInfo = item.basic_info || item;
      uniqueId = basicInfo.author_unique_id || basicInfo.user_unique_id;
      nickname = basicInfo.author_nickname || basicInfo.user_nickname;
      videoId = item.video_id || '';
    }
    
    if (uniqueId && uniqueId.trim() && uniqueId !== 'None') {
      unique.set(uniqueId, {
        author_unique_id: uniqueId.trim(),
        author_nickname: nickname?.trim() || '',
        video_id: videoId || '',
        raw_data: item
      });
    }
  });
  
  return Array.from(unique.values());
}

async function analyzeCreator(creator, taskId) {
  try {
    // 获取TikTok用户信息
    const userInfo = await getTikTokUserInfo(creator.author_unique_id);
    
    // 添加延迟避免API限制
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // 获取用户视频数据（简化版，减少API调用）
    const videos = await getTikTokUserPosts(creator.author_unique_id, 5);
    
    // 使用Gemini AI分析
    const analysis = await analyzeWithGemini(
      userInfo.signature || '',
      creator.author_nickname,
      creator.author_unique_id,
      userInfo
    );
    
    // 计算视频指标
    const metrics = calculateVideoMetrics(videos);
    
    return {
      video_id: creator.video_id,
      author_unique_id: creator.author_unique_id,
      author_link: `https://www.tiktok.com/@${creator.author_unique_id}`,
      signature: userInfo.signature || '',
      is_brand: analysis.is_brand,
      is_matrix_account: analysis.is_matrix_account,
      is_ugc_creator: analysis.is_ugc_creator,
      extracted_brand_name: analysis.brand_name || '',
      brand_confidence: analysis.brand_confidence || 0,
      analysis_details: analysis.analysis_details || '',
      author_followers_count: userInfo.followerCount || 0,
      author_followings_count: userInfo.followingCount || 0,
      videoCount: userInfo.videoCount || 0,
      author_avatar: userInfo.avatar || '',
      create_times: new Date().toISOString().split('T')[0],
      email: extractEmail(userInfo.signature || ''),
      recent_posts_views_avg: metrics.avgViews,
      recent_posts_like_avg: metrics.avgLikes,
      recent_posts_share_avg: metrics.avgShares,
      posting_frequency: metrics.postingFrequency,
      stability_score: metrics.stabilityScore
    };
    
  } catch (error) {
    console.error(`Analyze creator ${creator.author_unique_id} error:`, error);
    throw error;
  }
}

async function getTikTokUserInfo(uniqueId) {
  const RAPIDAPI_KEY = '34ba1ae26fmsha15de959b0b5d6ep11e6e6jsn64ad77705138';
  
  try {
    const response = await fetch(
      `https://tiktok-scraper7.p.rapidapi.com/user/info?unique_id=${uniqueId}`,
      {
        headers: {
          'x-rapidapi-key': RAPIDAPI_KEY,
          'x-rapidapi-host': 'tiktok-scraper7.p.rapidapi.com'
        }
      }
    );
    
    if (response.ok) {
      const data = await response.json();
      if (data.code === 0 && data.data) {
        const user = data.data.user || {};
        const stats = data.data.stats || {};
        return {
          signature: user.signature || '',
          followerCount: stats.followerCount || 0,
          followingCount: stats.followingCount || 0,
          videoCount: stats.videoCount || 0,
          avatar: user.avatarThumb || ''
        };
      }
    }
  } catch (error) {
    console.error(`TikTok API error for ${uniqueId}:`, error);
  }
  
  return {
    signature: '',
    followerCount: 0,
    followingCount: 0,
    videoCount: 0,
    avatar: ''
  };
}

async function getTikTokUserPosts(uniqueId, count = 5) {
  const RAPIDAPI_KEY = '34ba1ae26fmsha15de959b0b5d6ep11e6e6jsn64ad77705138';
  
  try {
    const response = await fetch(
      `https://tiktok-scraper7.p.rapidapi.com/user/posts?unique_id=${uniqueId}&count=${count}`,
      {
        headers: {
          'x-rapidapi-key': RAPIDAPI_KEY,
          'x-rapidapi-host': 'tiktok-scraper7.p.rapidapi.com'
        }
      }
    );
    
    if (response.ok) {
      const data = await response.json();
      if (data.code === 0 && data.data?.videos) {
        return data.data.videos.map(video => ({
          video_id: video.video_id || '',
          title: video.title || '',
          play_count: video.play_count || 0,
          digg_count: video.digg_count || 0,
          share_count: video.share_count || 0,
          create_time: video.create_time || 0
        }));
      }
    }
  } catch (error) {
    console.error(`TikTok Posts API error for ${uniqueId}:`, error);
  }
  
  return [];
}

async function analyzeWithGemini(signature, nickname, uniqueId, userInfo) {
  const GEMINI_API_KEY = 'AIzaSyB8GkbKtlc9OfyHE2c_wasXpCatYRC11IY';
  
  const prompt = `Analyze this TikTok creator profile and classify them:

Username: ${uniqueId}
Display Name: ${nickname}
Bio/Signature: ${signature}
Followers: ${userInfo.followerCount || 0}

Classify into ONE category:
1. OFFICIAL_BRAND: Official brand/company accounts
2. MATRIX_ACCOUNT: Creator affiliated with specific brand/business  
3. UGC_CREATOR: Regular creators (with or without brand partnerships)

Respond with exactly 6 values separated by pipes:
1. OFFICIAL_BRAND [True/False]
2. MATRIX_ACCOUNT [True/False]
3. UGC_CREATOR [True/False] 
4. Brand Name [Specific brand name or "None"]
5. Confidence Score [0.0-1.0]
6. Analysis Details [Brief explanation]

Example: True|False|False|Nike|0.95|Official Nike account`;

  try {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          contents: [{
            parts: [{
              text: prompt
            }]
          }]
        })
      }
    );

    if (response.ok) {
      const data = await response.json();
      const responseText = data.candidates?.[0]?.content?.parts?.[0]?.text;
      
      if (responseText) {
        const parts = responseText.split('|').map(p => p.trim());
        if (parts.length === 6) {
          return {
            is_brand: parts[0].toLowerCase() === 'true',
            is_matrix_account: parts[1].toLowerCase() === 'true',
            is_ugc_creator: parts[2].toLowerCase() === 'true',
            brand_name: parts[3] !== 'None' ? parts[3] : '',
            brand_confidence: parseFloat(parts[4]) || 0,
            analysis_details: parts[5]
          };
        }
      }
    }
  } catch (error) {
    console.error(`Gemini API error for ${uniqueId}:`, error);
  }
  
  // 如果Gemini分析失败，使用规则分析
  return analyzeWithRules(signature, nickname, uniqueId, userInfo);
}

function analyzeWithRules(signature, nickname, uniqueId, userInfo) {
  const sig = signature.toLowerCase();
  const name = nickname.toLowerCase();
  const id = uniqueId.toLowerCase();
  
  // 官方品牌关键词
  const brandKeywords = ['official', 'brand', 'company', '.com', '.id', '.app'];
  const hasBrandKeywords = brandKeywords.some(keyword => 
    id.includes(keyword) || sig.includes(keyword)
  );
  
  // 商业关键词
  const businessKeywords = ['shop', 'store', 'salon', 'barber', 'restaurant'];
  const hasBusinessKeywords = businessKeywords.some(keyword => 
    sig.includes(keyword)
  );
  
  if (hasBrandKeywords) {
    return {
      is_brand: true,
      is_matrix_account: false,
      is_ugc_creator: false,
      brand_name: extractBrandName(uniqueId, signature),
      brand_confidence: 0.7,
      analysis_details: 'Rule-based: Official brand indicators detected'
    };
  } else if (hasBusinessKeywords) {
    return {
      is_brand: false,
      is_matrix_account: true,
      is_ugc_creator: false,
      brand_name: extractBusinessName(signature),
      brand_confidence: 0.6,
      analysis_details: 'Rule-based: Business/matrix account indicators detected'
    };
  } else {
    return {
      is_brand: false,
      is_matrix_account: false,
      is_ugc_creator: true,
      brand_name: '',
      brand_confidence: 0.8,
      analysis_details: 'Rule-based: Regular creator account'
    };
  }
}

function extractBrandName(uniqueId, signature) {
  // 简化的品牌名提取
  if (uniqueId.includes('.')) {
    return uniqueId.split('.')[0].replace(/[^a-zA-Z0-9]/g, '');
  }
  return uniqueId.replace(/[^a-zA-Z0-9]/g, '');
}

function extractBusinessName(signature) {
  // 简化的商业名称提取
  const match = signature.match(/([a-zA-Z\s]+(?:shop|store|salon|barber|restaurant))/i);
  return match ? match[1].trim() : '';
}

function extractEmail(signature) {
  const emailMatch = signature.match(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/);
  return emailMatch ? emailMatch[0] : '';
}

function calculateVideoMetrics(videos) {
  if (!videos || videos.length === 0) {
    return {
      avgViews: 0,
      avgLikes: 0,
      avgShares: 0,
      postingFrequency: 0,
      stabilityScore: 0
    };
  }
  
  const totalViews = videos.reduce((sum, v) => sum + (v.play_count || 0), 0);
  const totalLikes = videos.reduce((sum, v) => sum + (v.digg_count || 0), 0);
  const totalShares = videos.reduce((sum, v) => sum + (v.share_count || 0), 0);
  
  return {
    avgViews: Math.round(totalViews / videos.length),
    avgLikes: Math.round(totalLikes / videos.length),
    avgShares: Math.round(totalShares / videos.length),
    postingFrequency: videos.length / 30, // 假设是30天内的视频
    stabilityScore: 0.5 // 简化计算
  };
}

function generateStatistics(results) {
  const total = results.length;
  const brandRelated = results.filter(r => 
    r.is_brand || r.is_matrix_account || (r.extracted_brand_name && r.extracted_brand_name.trim())
  );
  const nonBrand = results.filter(r => !brandRelated.includes(r));
  
  const officialAccounts = results.filter(r => r.is_brand);
  const matrixAccounts = results.filter(r => r.is_matrix_account);
  const ugcCreators = results.filter(r => r.is_ugc_creator);
  
  const brandInRelated = brandRelated.filter(r => r.is_brand);
  const matrixInRelated = brandRelated.filter(r => r.is_matrix_account);
  const ugcInRelated = brandRelated.filter(r => r.is_ugc_creator);
  
  return {
    total_processed: total,
    brand_related_count: brandRelated.length,
    non_brand_count: nonBrand.length,
    official_account_count: officialAccounts.length,
    matrix_account_count: matrixAccounts.length,
    ugc_creator_count: ugcCreators.length,
    non_branded_creator_count: nonBrand.length,
    official_account_percentage: total > 0 ? Math.round((officialAccounts.length / total) * 100) : 0,
    matrix_account_percentage: total > 0 ? Math.round((matrixAccounts.length / total) * 100) : 0,
    ugc_creator_percentage: total > 0 ? Math.round((ugcCreators.length / total) * 100) : 0,
    non_branded_creator_percentage: total > 0 ? Math.round((nonBrand.length / total) * 100) : 0,
    brand_in_related: brandInRelated.length,
    matrix_in_related: matrixInRelated.length,
    ugc_in_related: ugcInRelated.length,
    brand_in_related_percentage: brandRelated.length > 0 ? Math.round((brandInRelated.length / brandRelated.length) * 100) : 0,
    matrix_in_related_percentage: brandRelated.length > 0 ? Math.round((matrixInRelated.length / brandRelated.length) * 100) : 0,
    ugc_in_related_percentage: brandRelated.length > 0 ? Math.round((ugcInRelated.length / brandRelated.length) * 100) : 0,
    brand_file: 'brand_related_creators.csv',
    non_brand_file: 'non_brand_creators.csv',
    detailed_results: results
  };
}
