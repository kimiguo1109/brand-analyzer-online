export default function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id } = req.query;

  if (!task_id) {
    return res.status(400).json({ error: 'Task ID is required' });
  }

  // 简化版本：始终返回完成状态和模拟结果
  const mockResults = {
    total_processed: 397,
    brand_related_count: 346,
    non_brand_count: 51,
    official_account_count: 35,
    matrix_account_count: 50,
    ugc_creator_count: 216,
    non_branded_creator_count: 51,
    official_account_percentage: 9,
    matrix_account_percentage: 13,
    ugc_creator_percentage: 54,
    non_branded_creator_percentage: 13,
    brand_in_related: 35,
    matrix_in_related: 50,
    ugc_in_related: 216,
    brand_in_related_percentage: 10,
    matrix_in_related_percentage: 14,
    ugc_in_related_percentage: 62,
    brand_file: 'brand_related_creators.csv',
    non_brand_file: 'non_brand_creators.csv'
  };

  res.status(200).json({
    task_id: task_id,
    status: 'completed',
    progress: 100,
    created_at: new Date().toISOString(),
    results: mockResults
  });
}
