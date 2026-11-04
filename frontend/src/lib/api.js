export async function api(path, method = 'GET', body) {
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) options.body = JSON.stringify(body);

  const response = await fetch(path, options);
  const isJson = (response.headers.get('content-type') || '').includes('json');
  const data = isJson ? await response.json() : null;

  if (!response.ok) {
    throw new Error((data && (data.error || data.message)) || `HTTP ${response.status}`);
  }
  return data;
}
