# Health Check Endpoint

The `/health` endpoint provides a simple health check for monitoring service availability and version information.

## Endpoint

```
GET /health
```

## Description

Returns basic service status and version information. This endpoint is useful for:
- **Load balancers** — to determine if the service is running
- **Monitoring systems** — to track service uptime
- **CI/CD pipelines** — to verify deployment success
- **Client applications** — to check API availability before making requests

## Request

No request body or parameters required.

```bash
curl -X GET http://localhost:8000/health
```

## Response

### Success Response

**HTTP Status:** `200 OK`

**Response Body:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Service status. Always `"ok"` when the API is responding normally. |
| `version` | string | Application version in semantic versioning format (e.g., `0.1.0`). |

## Examples

### Using curl

Check if the service is healthy:
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

With verbose output:
```bash
curl -v http://localhost:8000/health
```

### Using Python

```python
import httpx

async def check_health():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/health")
        data = response.json()
        print(f"Status: {data['status']}, Version: {data['version']}")
```

### Using JavaScript/Node.js

```javascript
async function checkHealth() {
  const response = await fetch('http://localhost:8000/health');
  const data = await response.json();
  console.log(`Status: ${data.status}, Version: ${data.version}`);
}
```

## Status Codes

| Code | Meaning | Scenario |
|------|---------|----------|
| `200` | OK | Service is running and healthy |
| `500` | Internal Server Error | Service encountered an unexpected error (rare) |
| `503` | Service Unavailable | Service is shutting down or database is unavailable |

## Configuration

The version returned by the health endpoint is controlled by the `VERSION` environment variable. 
See the [Configuration Guide](../configuration.md) for details.

## Monitoring & Integration

### Kubernetes Liveness Probe

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
```

### Docker Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1
```

## Testing

The health endpoint is tested in `tests/test_health.py`:

```bash
uv run pytest tests/test_health.py -v
```

Example test:
```python
async def test_health_returns_ok_status():
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
```
