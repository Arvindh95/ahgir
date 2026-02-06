# Implementation Plan: PicUr

## Overview

This implementation plan breaks down the PicUr multi-tenant wedding photo sharing platform into incremental coding tasks. The system will be built using FastAPI (backend), Next.js (frontend), PostgreSQL with pgvector (database), MinIO (object storage), and RQ workers (background processing). Each task builds on previous work, with property-based tests integrated throughout to validate correctness properties early.

## Tasks

- [x] 1. Set up project structure and infrastructure
  - Create backend directory structure (app/, tests/, migrations/)
  - Create frontend directory structure (pages/, components/, lib/)
  - Set up Docker Compose with PostgreSQL (with pgvector), MinIO, Redis, Caddy
  - Configure environment variables for all services
  - Create Alembic migration setup for database schema
  - Set up pytest with Hypothesis for property-based testing
  - _Requirements: 14.1, 14.2, 14.3, 14.5_

- [x] 2. Implement database models and migrations
  - [x] 2.1 Create SQLAlchemy models for users, events, images, faces, guest_sessions, audit_logs, rate_limits
    - Define all table schemas with proper relationships and indexes
    - Add pgvector extension and vector column type for face embeddings
    - _Requirements: 1.1, 2.1, 3.5, 4.4, 5.4, 12.1_
  
  - [x] 2.2 Create Alembic migration scripts
    - Generate initial migration for all tables
    - Add vector similarity index (ivfflat) for faces table
    - _Requirements: 14.4_
  
  - [x] 2.3 Write unit tests for database models
    - Test model creation and relationships
    - Test unique constraints and cascading deletes
    - _Requirements: 1.1, 2.1, 3.5, 4.4_

- [x] 3. Implement authentication service
  - [x] 3.1 Create Admin registration and login endpoints
    - Implement POST /auth/register with bcrypt password hashing
    - Implement POST /auth/login with JWT token generation
    - Implement GET /auth/me for token validation
    - _Requirements: 1.1, 1.2, 1.3_
  
  - [x] 3.2 Create JWT middleware for Admin authentication
    - Extract and validate JWT tokens from Authorization header
    - Inject user_id into request context
    - _Requirements: 1.3_
  
  - [x] 3.3 Create Event_Token generation for Guest sessions
    - Implement token generation with event_id scope
    - Create middleware for Event_Token validation
    - _Requirements: 5.4, 5.5_
  
  - [x] 3.4 Write property test for JWT token expiration
    - **Property 6: JWT Token Expiration**
    - **Validates: Requirements 1.3, 5.6**
  
  - [x] 3.5 Write unit tests for authentication
    - Test registration with duplicate email
    - Test login with invalid credentials
    - Test token validation with malformed tokens
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 4. Implement Event management service
  - [x] 4.1 Create Event CRUD endpoints
    - Implement POST /events with slug generation and QR code creation
    - Implement GET /events with owner_user_id filtering
    - Implement GET /events/{event_id} with ownership validation
    - Implement GET /events/{event_id}/qr for QR code image
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  
  - [x] 4.2 Implement Event status tracking
    - Add endpoint to return photo counts by status
    - Calculate indexing percentage
    - Return total face count
    - _Requirements: 9.1, 9.2, 9.4, 9.5_
  
  - [x] 4.3 Write property test for Admin isolation
    - **Property 1: Admin Isolation**
    - **Validates: Requirements 1.4, 1.5, 7.5**
  
  - [x] 4.4 Write unit tests for Event management
    - Test Event creation with all fields
    - Test slug uniqueness
    - Test ownership filtering
    - _Requirements: 2.1, 2.2, 2.5, 2.6_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement MinIO storage service
  - [x] 6.1 Create MinIO client wrapper
    - Initialize MinIO client with credentials
    - Create bucket if not exists
    - Implement upload_photo, get_photo, delete_photo methods
    - _Requirements: 3.1, 3.2_
  
  - [x] 6.2 Implement presigned URL generation
    - Create method to generate presigned URLs with expiry
    - Add validation to check image belongs to event
    - _Requirements: 6.6, 7.3_
  
  - [x] 6.3 Write property test for presigned URL validation
    - **Property 5: Presigned URL Validation**
    - **Validates: Requirements 7.3**
  
  - [x] 6.4 Write unit tests for storage service
    - Test upload and retrieval
    - Test presigned URL generation
    - Test error handling for missing files
    - _Requirements: 3.1, 3.2, 6.6_

- [x] 7. Implement photo upload service
  - [x] 7.1 Create photo upload endpoint
    - Implement POST /events/{event_id}/photos with multipart form data
    - Validate ownership (owner_user_id matches JWT)
    - Validate image formats (JPEG, PNG)
    - Compute SHA256 hash for deduplication
    - Store original in MinIO at events/{eventId}/original/{imageId}.jpg
    - _Requirements: 3.1, 3.4, 3.5, 3.6, 10.5_
  
  - [x] 7.2 Implement thumbnail generation
    - Use Pillow to resize images to 512px width
    - Store thumbnails in MinIO at events/{eventId}/thumb/{imageId}.jpg
    - _Requirements: 3.2_
  
  - [x] 7.3 Implement EXIF metadata extraction
    - Extract EXIF data using Pillow
    - Store as JSONB in image record
    - _Requirements: 3.3_
  
  - [x] 7.4 Create photo listing and deletion endpoints
    - Implement GET /events/{event_id}/photos with pagination and status filtering
    - Implement DELETE /events/{event_id}/photos/{image_id} with ownership validation
    - _Requirements: 3.6_
  
  - [x] 7.5 Write property test for photo hash deduplication
    - **Property 4: Photo Hash Deduplication**
    - **Validates: Requirements 3.4**
  
  - [x] 7.6 Write property test for ownership validation on upload
    - **Property 12: Ownership Validation on Upload**
    - **Validates: Requirements 3.6**
  
  - [x] 7.7 Write unit tests for photo upload
    - Test successful upload
    - Test duplicate rejection
    - Test invalid format rejection
    - Test unauthorized upload attempt
    - _Requirements: 3.1, 3.4, 3.5, 3.6, 10.5_

- [x] 8. Implement face indexing worker
  - [x] 8.1 Set up RQ worker infrastructure
    - Create RQ queue configuration
    - Create worker entry point
    - Add job queuing after photo upload
    - _Requirements: 4.1_
  
  - [x] 8.2 Implement CompreFace face detection
    - Initialize CompreFace with buffalo_l model
    - Create face detection function that processes image and returns faces
    - Extract 512-dim embeddings, bounding boxes, and quality scores
    - _Requirements: 4.2, 4.3_
  
  - [x] 8.3 Create face indexing job handler
    - Download photo from MinIO
    - Detect faces using CompreFace
    - Store face embeddings in database with event_id
    - Update image status to 'indexed', 'no_faces', or 'failed'
    - _Requirements: 4.1, 4.4, 4.5, 4.6, 4.7_
  
  - [x] 8.4 Implement reindex endpoint
    - Create POST /events/{event_id}/reindex
    - Reset all image statuses to 'pending'
    - Queue all images for reprocessing
    - _Requirements: 9.3_
  
  - [x] 8.5 Write property test for face embedding consistency
    - **Property 10: Face Embedding Consistency**
    - **Validates: Requirements 4.2, 4.3**
  
  - [x] 8.6 Write property test for status transition validity
    - **Property 13: Status Transition Validity**
    - **Validates: Requirements 4.5, 4.6**
  
  - [x] 8.7 Write unit tests for face indexing
    - Test face detection with multiple faces
    - Test no faces detected scenario
    - Test error handling and retry logic
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Guest access service
  - [x] 10.1 Create Guest Event access endpoints
    - Implement GET /e/{slug} to retrieve Event by slug
    - Implement POST /e/{slug}/auth for passcode verification
    - Generate Event_Token on successful authentication
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [x] 10.2 Write property test for Event Token scoping
    - **Property 2: Event Token Scoping**
    - **Validates: Requirements 5.5, 7.1, 7.4**
  
  - [x] 10.3 Write property test for passcode verification
    - **Property 7: Passcode Verification**
    - **Validates: Requirements 5.2, 5.3**
  
  - [x] 10.4 Write unit tests for Guest access
    - Test Event access with valid slug
    - Test Event access with invalid slug
    - Test passcode verification success and failure
    - Test Event_Token generation
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 11. Implement face matching service
  - [x] 11.1 Create face scan endpoint
    - Implement POST /scan with Event_Token authentication
    - Accept base64 encoded face image from camera
    - Detect face and compute embedding using CompreFace
    - _Requirements: 6.1, 6.2_
  
  - [x] 11.2 Implement vector similarity search
    - Query faces table using pgvector cosine similarity
    - Filter by event_id from Event_Token
    - Apply similarity threshold (default 0.6)
    - Return top 50 matches ordered by similarity
    - _Requirements: 6.3, 6.4, 6.5_
  
  - [x] 11.3 Generate presigned URLs for matched photos
    - Create presigned URLs for thumbnails and originals
    - Add download URLs if allow_downloads is enabled
    - Set expiry to 15 minutes
    - _Requirements: 6.6, 8.1, 8.2, 8.3_
  
  - [x] 11.4 Write property test for face search isolation
    - **Property 3: Face Search Isolation**
    - **Validates: Requirements 6.3, 7.1, 7.2**
  
  - [x] 11.5 Write property test for vector search threshold
    - **Property 15: Vector Search Threshold**
    - **Validates: Requirements 6.4**
  
  - [x] 11.6 Write property test for download permission enforcement
    - **Property 9: Download Permission Enforcement**
    - **Validates: Requirements 8.4**
  
  - [x] 11.7 Write unit tests for face matching
    - Test successful face scan with matches
    - Test face scan with no matches
    - Test face scan with no face detected
    - Test download URL generation based on allow_downloads
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 8.1, 8.3, 8.4_

- [x] 12. Implement rate limiting service
  - [x] 12.1 Create rate limiting middleware
    - Use Redis to track scan counts per session
    - Implement sliding window algorithm
    - Enforce 10 scans per hour limit
    - Return 429 error with Retry-After header when exceeded
    - _Requirements: 10.1, 10.2_
  
  - [x] 12.2 Write property test for rate limit enforcement
    - **Property 8: Rate Limit Enforcement**
    - **Validates: Requirements 10.1, 10.2**
  
  - [x] 12.3 Write unit tests for rate limiting
    - Test scan count tracking
    - Test limit enforcement
    - Test window reset behavior
    - _Requirements: 10.1, 10.2_

- [x] 13. Implement audit logging service
  - [x] 13.1 Create audit logging functions
    - Implement log_action function to create audit log entries
    - Add logging to all Admin and Guest actions
    - Store metadata as JSONB
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  
  - [x] 13.2 Create audit log query endpoint
    - Implement GET /events/{event_id}/logs with pagination
    - Filter by action type
    - Enforce ownership validation
    - _Requirements: 12.5, 12.6_
  
  - [x] 13.3 Write property test for audit log immutability
    - **Property 14: Audit Log Immutability**
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4**
  
  - [x] 13.4 Write unit tests for audit logging
    - Test log creation for various actions
    - Test log querying with filters
    - Test cross-tenant access prevention
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 14. Implement data retention and cleanup
  - [x] 14.1 Create Event deletion endpoint
    - Implement DELETE /events/{event_id} with ownership validation
    - Delete all images from MinIO (originals and thumbnails)
    - Cascade delete images, faces, sessions, and audit logs from database
    - _Requirements: 11.3, 11.4, 11.5_
  
  - [x] 14.2 Create retention policy background job
    - Create scheduled job to check for expired Events
    - Mark Events past retention_days for deletion
    - Execute deletion process
    - _Requirements: 11.1, 11.2_
  
  - [x] 14.3 Write property test for Event deletion cascade
    - **Property 11: Event Deletion Cascade**
    - **Validates: Requirements 11.3, 11.4, 11.5**
  
  - [x] 14.4 Write unit tests for data retention
    - Test Event deletion with all cascades
    - Test retention policy enforcement
    - Test audit log creation for deletions
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Implement frontend Admin dashboard
  - [x] 16.1 Create Admin authentication pages
    - Build registration page with form validation
    - Build login page with JWT token storage
    - Implement protected route wrapper
    - _Requirements: 1.1, 1.2_
  
  - [x] 16.2 Create Event management pages
    - Build Event list page showing all Admin's Events
    - Build Event creation form with all fields
    - Display Event details with status and QR code
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 9.1, 9.2_
  
  - [x] 16.3 Create photo upload interface
    - Build bulk upload component with drag-and-drop
    - Show upload progress and results
    - Display photo grid with status indicators
    - _Requirements: 3.1, 3.2, 3.3_
  
  - [x] 16.4 Create Event monitoring dashboard
    - Display indexing progress with percentage
    - Show photo counts by status
    - Add reindex button
    - Display audit logs
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 12.5_

- [x] 17. Implement frontend Guest scanner interface
  - [x] 17.1 Create Guest Event access page
    - Build Event landing page at /e/{slug}
    - Display Event name and date
    - Add passcode input if required
    - _Requirements: 5.1, 5.2_
  
  - [x] 17.2 Create face scanning interface
    - Implement WebRTC camera access
    - Capture 1-3 frames from camera
    - Send frames to backend for matching
    - _Requirements: 6.1_
  
  - [x] 17.3 Create photo results gallery
    - Display matched photos in grid layout
    - Show similarity scores
    - Add download buttons if allowed
    - Handle empty results gracefully
    - _Requirements: 6.5, 6.7, 8.1, 8.4_

- [x] 18. Implement error handling and logging
  - [x] 18.1 Create global error handler
    - Implement consistent error response format
    - Map exceptions to appropriate HTTP status codes
    - Log all errors with context
    - _Requirements: 10.3, 10.4_
  
  - [x] 18.2 Add retry logic for external services
    - Implement exponential backoff for MinIO operations
    - Add retry logic for face detection failures
    - _Requirements: 4.1_
  
  - [x] 18.3 Write unit tests for error handling
    - Test all error response formats
    - Test retry logic
    - Test error logging
    - _Requirements: 10.3, 10.4_

- [x] 19. Implement health checks and monitoring
  - [x] 19.1 Create health check endpoints
    - Add /health endpoint for API
    - Check database connectivity
    - Check MinIO connectivity
    - Check Redis connectivity
    - _Requirements: 14.5_
  
  - [x] 19.2 Write unit tests for health checks
    - Test health endpoint responses
    - Test failure scenarios
    - _Requirements: 14.5_

- [x] 20. Final integration and deployment setup
  - [x] 20.1 Configure Caddy reverse proxy
    - Set up Caddyfile with automatic HTTPS
    - Configure routes for frontend and backend
    - _Requirements: 14.3_
  
  - [x] 20.2 Create production Docker Compose configuration
    - Set up production environment variables
    - Configure resource limits
    - Add restart policies
    - _Requirements: 14.1, 14.6_
  
  - [x] 20.3 Create deployment documentation
    - Document environment variables
    - Document deployment steps
    - Document backup procedures
    - _Requirements: 14.6_
  
  - [x] 20.4 Write integration tests for end-to-end flows
    - Test complete Admin upload flow
    - Test complete Guest scan flow
    - Test background processing flow
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1_

- [x] 21. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Property-based tests use Hypothesis with minimum 100 iterations
- All property tests are tagged with: `# Feature: picur, Property {N}: {property_text}`
- Integration tests require full Docker Compose environment
- Frontend tasks can be implemented in parallel with backend tasks after task 5
