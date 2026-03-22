# API Reference

Welcome to the openOrbit API reference. 

## Available Endpoints

- [Health Check](./health.md) — `GET /health` — Service status and version

## Auto-Generated Documentation

The API also provides interactive documentation at:

- **Swagger UI** — http://localhost:8000/docs
- **ReDoc** — http://localhost:8000/redoc
- **OpenAPI Schema** — http://localhost:8000/openapi.json

## Authentication

PO-001 does not include authentication. Future sprints will add:
- JWT token-based authentication
- API key management
- Role-based access control (RBAC)

## Response Format

All responses are JSON:

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Error Handling

The API returns standard HTTP status codes:

| Status | Meaning |
|--------|---------|
| 200 | OK — Request succeeded |
| 400 | Bad Request — Invalid parameters |
| 404 | Not Found — Resource doesn't exist |
| 500 | Server Error — Internal error |
| 503 | Unavailable — Service is down |

Error responses include a message:

```json
{
  "detail": "Resource not found"
}
```

## Rate Limiting

PO-001 does not implement rate limiting. Future versions will add:
- Per-IP rate limiting
- Per-API-key rate limiting
- Adaptive throttling based on server load

## Pagination

PO-001 endpoints do not use pagination. Future list endpoints will support:

```
GET /launches?skip=0&limit=10
```

## See Also

- [Configuration Guide](../configuration.md)
- [Development Guide](../development.md)
- [Architecture](../architecture.md)
