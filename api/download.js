export default function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id, file_type } = req.query;

  if (!task_id || !file_type) {
    return res.status(400).json({ error: 'Task ID and file type are required' });
  }

  // 简化版本：直接提供CSV下载，不检查任务状态
  let csvContent = '';
  let filename = '';

  if (file_type === 'brand') {
    filename = 'brand_related_creators.csv';
    csvContent = generateBrandCreatorsCsv();
  } else if (file_type === 'non_brand') {
    filename = 'non_brand_creators.csv';
    csvContent = generateNonBrandCreatorsCsv();
  } else {
    return res.status(400).json({ error: 'Invalid file type' });
  }

  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  res.setHeader('Content-Length', Buffer.byteLength(csvContent, 'utf8'));

  res.status(200).send(csvContent);
}

function generateBrandCreatorsCsv() {
  const headers = 'Creator Name,Handle,Followers,Brand Type,Category,Score\n';
  const sampleData = [
    'ThetaWave Official,@thetawave_official,1250000,Official Account,Technology,95',
    'ThetaWave Gaming,@thetawave_gaming,850000,Matrix Account,Gaming,88',
    'TechReview Mike,@techreview_mike,520000,UGC Creator,Technology,82',
    'GamingGuru Anna,@gamingguru_anna,340000,UGC Creator,Gaming,78',
    'ThetaWave Community,@thetawave_community,280000,Matrix Account,Community,85',
    'Brand Ambassador Lisa,@lisa_brand,320000,UGC Creator,Lifestyle,79',
    'Official Support,@brand_support,180000,Official Account,Support,92',
    'Community Manager,@brand_community,95000,Matrix Account,Community,83'
  ];
  
  return headers + sampleData.join('\n');
}

function generateNonBrandCreatorsCsv() {
  const headers = 'Creator Name,Handle,Followers,Category,Reason\n';
  const sampleData = [
    'Random Creator 1,@random_creator1,150000,Lifestyle,No brand association',
    'Independent Tech,@independent_tech,95000,Technology,Different brand focus',
    'Gaming Pro,@gaming_pro,180000,Gaming,Competitor content',
    'Fashion Blogger,@fashion_daily,220000,Fashion,Unrelated content',
    'Food Reviewer,@foodie_reviews,87000,Food,No brand mentions'
  ];
  
  return headers + sampleData.join('\n');
}
