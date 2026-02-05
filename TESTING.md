# Testing Guide for PicUr

## Overview

This document explains how to run tests for the PicUr project. The tests are designed to run in a Docker environment where all dependencies (InsightFace, PostgreSQL with pgvector, MinIO, Redis) are properly configured.

## Prerequisites

- Docker and Docker Compose installed
- Ports 5433, 6379, 9000, 9001 available

## Running Tests

### Option 1: Using the Test Script (Recommended)

**On Linux/Mac:**
```bash
chmod +x run_tests_docker.sh
./run_tests_docker.sh
```

**On Windows:**
```cmd
run_tests_docker.bat
```

### Option 2: Manual Docker Commands

1. **Start required services:**
```bash
docker-compose up -d postgres redis minio
```

2. **Wait for services to be healthy (about 10 seconds):**
```bash
docker-compose ps
```

3. **Run database migrations:**
```bash
docker-compose run --rm backend alembic upgrade head
```

4. **Run all tests:**
```bash
docker-compose run --rm backend pytest -v
```

5. **Run specific test files:**
```bash
# Face indexing tests
docker-compose run --rm backend pytest backend/tests/test_face_indexing.py -v

# Property-based tests
docker-compose run --rm backend pytest backend/tests/test_face_indexing_properties.py -v

# Reindex endpoint tests
docker-compose run --rm backend pytest backend/tests/test_reindex.py -v
```

6. **Stop services:**
```bash
docker-compose down
```

## Test Categories

### Unit Tests
- `test_face_indexing.py` - Tests for face detection and indexing worker
- `test_reindex.py` - Tests for the reindex endpoint
- `test_auth.py` - Authentication tests
- `test_events.py` - Event management tests
- `test_photos.py` - Photo upload tests
- `test_storage.py` - MinIO storage tests

### Property-Based Tests
- `test_face_indexing_properties.py` - Property tests for face indexing:
  - Property 10: Face Embedding Consistency
  - Property 13: Status Transition Validity
- `test_events_properties.py` - Property tests for events
- `test_photos_properties.py` - Property tests for photos
- `test_storage_properties.py` - Property tests for storage

## Running Property-Based Tests

Property-based tests use Hypothesis to generate test cases. They run 100 iterations by default:

```bash
docker-compose run --rm backend pytest backend/tests/test_face_indexing_properties.py::test_face_embedding_consistency -v
docker-compose run --rm backend pytest backend/tests/test_face_indexing_properties.py::test_status_transition_validity -v
```

## Troubleshooting

### Tests Fail Due to Missing Dependencies

If you see import errors, ensure you're running tests inside Docker:
```bash
docker-compose run --rm backend pytest -v
```

### Database Connection Errors

Ensure PostgreSQL is running and healthy:
```bash
docker-compose ps postgres
docker-compose logs postgres
```

### MinIO Connection Errors

Ensure MinIO is running:
```bash
docker-compose ps minio
docker-compose logs minio
```

### Redis Connection Errors

Ensure Redis is running:
```bash
docker-compose ps redis
docker-compose logs redis
```

## Test Coverage

To generate a coverage report:
```bash
docker-compose run --rm backend pytest --cov=app --cov-report=html
```

The coverage report will be generated in `htmlcov/index.html`.

## Continuous Integration

The tests are designed to run in CI/CD pipelines. Example GitHub Actions workflow:

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: |
          docker-compose up -d postgres redis minio
          sleep 10
          docker-compose run --rm backend alembic upgrade head
          docker-compose run --rm backend pytest -v
          docker-compose down
```

## Notes

- Property-based tests may take longer to run (100 iterations each)
- Face detection tests require the InsightFace buffalo_l model to be downloaded on first run
- Some tests create temporary files in MinIO that are cleaned up automatically


## Integration Tests

### End-to-End Integration Tests

The `test_integration_e2e.py` file contains comprehensive end-to-end integration tests that validate complete workflows:

#### Test Classes

1. **TestAdminUploadFlow** - Complete Admin workflow
   - Register → Login → Create Event → Upload Photos → Check Status
   - Validates: Requirements 1.1, 2.1, 3.1

2. **TestGuestScanFlow** - Complete Guest workflow
   - Access Event → Enter Passcode → Scan Face → View Matches → Download
   - Validates: Requirements 5.1, 6.1

3. **TestBackgroundProcessingFlow** - Background processing workflow
   - Upload Photo → Queue Job → Process Face → Update Status
   - Validates: Requirements 4.1

4. **TestCrossFlowIntegration** - Cross-flow integration tests
   - Multi-admin isolation
   - Guest event isolation
   - Cross-tenant access prevention

### Running Integration Tests

**Run all integration tests:**
```bash
docker-compose run --rm backend pytest backend/tests/test_integration_e2e.py -v -m integration
```

**Or use the provided script:**
```bash
chmod +x scripts/run-integration-tests.sh
./scripts/run-integration-tests.sh
```

**Run specific integration test class:**
```bash
docker-compose run --rm backend pytest backend/tests/test_integration_e2e.py::TestAdminUploadFlow -v
docker-compose run --rm backend pytest backend/tests/test_integration_e2e.py::TestGuestScanFlow -v
docker-compose run --rm backend pytest backend/tests/test_integration_e2e.py::TestBackgroundProcessingFlow -v
```

### Integration Test Requirements

Integration tests require:
- All services running (postgres, redis, minio)
- Database migrations applied
- Sufficient resources for face detection (if not mocked)

### Test Markers

Tests are marked with pytest markers for easy filtering:

- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.property_test` - Property-based tests
- `@pytest.mark.slow` - Slow-running tests

**Run tests by marker:**
```bash
# Only integration tests
docker-compose run --rm backend pytest -m integration

# Only property tests
docker-compose run --rm backend pytest -m property_test

# Exclude slow tests
docker-compose run --rm backend pytest -m "not slow"

# Unit tests only (exclude property and integration)
docker-compose run --rm backend pytest -m "not property_test and not integration"
```

## Complete Test Suite

### Run All Tests

To run the complete test suite including unit, property-based, and integration tests:

```bash
docker-compose run --rm backend pytest -v
```

### Expected Test Execution Times

- Unit tests: < 2 minutes
- Property tests: < 5 minutes
- Integration tests: < 10 minutes
- Total: < 20 minutes

### Test Summary

The complete test suite includes:
- **Unit Tests**: ~50+ tests covering individual components
- **Property Tests**: 15 property-based tests validating correctness properties
- **Integration Tests**: 6+ end-to-end workflow tests

Total test coverage target: 80%+
