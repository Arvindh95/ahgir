# PicUr - Multi-Tenant Wedding Photo Sharing Platform

PicUr is a wedding photo sharing platform that enables photographers to manage events where guests can discover their photos through live face recognition.

## Features

- Multi-tenant architecture with complete Admin isolation
- Event-based photo organization
- Live face recognition for guests
- Secure photo storage with MinIO
- Background face indexing with CompreFace
- Rate limiting and audit logging
- Docker-based deployment

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL with pgvector
- **Frontend**: Next.js, React, TypeScript
- **Storage**: MinIO (S3-compatible)
- **Queue**: Redis + RQ
- **Face Recognition**: CompreFace API
- **Reverse Proxy**: Caddy

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Node.js 20+

### Development Setup

1. Clone the repository
2. Copy environment files:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

3. Start all services:
   ```bash
   docker-compose up -d
   ```

4. Run database migrations:
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

   For production deployments via `scripts/deploy-vps.sh`, migrations run
   automatically before the backend/worker recreate step. No manual step
   is needed there.

5. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - MinIO Console: http://localhost:9001
   - CompreFace Admin: http://localhost:8082

### Running Tests

```bash
# Backend tests
docker-compose exec backend pytest

# Property-based tests
docker-compose exec backend pytest -m property_test

# Integration tests
docker-compose exec backend pytest -m integration
```

## Project Structure

```
picur/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── config.py
│   ├── tests/
│   │   ├── __init__.py
│   │   └── conftest.py
│   ├── migrations/
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic.ini
│   └── pytest.ini
├── frontend/
│   ├── pages/
│   │   ├── _app.tsx
│   │   └── index.tsx
│   ├── components/
│   ├── lib/
│   │   └── api.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.js
│   └── Dockerfile
├── docker-compose.yml
├── Caddyfile
└── README.md
```

## License

MIT
