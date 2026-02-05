@echo off
REM Script to run tests in Docker environment (Windows)

echo Building and starting Docker services...
docker-compose up -d postgres redis minio

echo Waiting for services to be healthy...
timeout /t 10 /nobreak

echo Running database migrations...
docker-compose run --rm backend alembic upgrade head

echo Running all tests...
docker-compose run --rm backend pytest -v

echo Running property-based tests specifically...
docker-compose run --rm backend pytest backend/tests/test_face_indexing_properties.py -v

echo Stopping services...
docker-compose down
