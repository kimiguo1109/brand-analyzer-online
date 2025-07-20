export default function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { task_id, file_type } = req.query;

  if (!task_id || !file_type) {
    return res.status(400).json({ error: 'Task ID and file type are required' });
  }

  const task = global.analysisTasksCache?.get(task_id);

  if (!task || task.status !== 'completed') {
    return res.status(400).json({ error: 'Task not completed yet' });
  }

  let csvContent = 'Creator Name,Handle,Followers,Brand Type\n';
  csvContent += 'Sample Creator,@sample,100000,UGC Creator\n';
  
  const filename = file_type === 'brand' ? 'brand_creators.csv' : 'non_brand_creators.csv';

  res.setHeader('Content-Type', 'text/csv');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  res.status(200).send(csvContent);
}
