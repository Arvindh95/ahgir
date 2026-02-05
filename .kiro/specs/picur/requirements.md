# Requirements Document: PicUr

## Introduction

PicUr is a multi-tenant wedding photo sharing platform that enables photographers and studios to manage events where guests can discover their photos through live face recognition. The system provides complete tenant and event isolation, ensuring that each photographer's events remain private and each event's photo database is independent.

## Glossary

- **Admin**: A photographer or studio account that owns and manages Events
- **Event**: A wedding or photo session with its own photo set, face database, and guest access link
- **Guest**: An attendee who scans their face to find photos from a specific Event
- **Face_Indexer**: Background worker that processes uploaded photos and extracts face embeddings
- **Storage_Service**: MinIO-based object storage for photos and thumbnails
- **Auth_Service**: JWT-based authentication system for Admin and Guest sessions
- **Vector_Database**: PostgreSQL with pgvector extension for face embedding similarity search
- **Event_Token**: Session token scoped to a specific Event for Guest access

## Requirements

### Requirement 1: Multi-Tenant Admin Authentication

**User Story:** As a photographer, I want to create my own account and manage my events independently, so that my business data remains private from other photographers.

#### Acceptance Criteria

1. WHEN a new photographer registers, THE Auth_Service SHALL create a unique Admin account with email and bcrypt-hashed password
2. WHEN an Admin logs in with valid credentials, THE Auth_Service SHALL return a JWT token containing the Admin's user_id
3. WHEN an Admin accesses any endpoint, THE System SHALL validate the JWT token and extract the user_id
4. THE System SHALL enforce that each Admin can only access Events where owner_user_id matches their user_id
5. WHEN an Admin attempts to access another Admin's Event, THE System SHALL return an authorization error

### Requirement 2: Event Creation and Management

**User Story:** As an Admin, I want to create and manage unlimited Events, so that I can organize photos for each wedding or session separately.

#### Acceptance Criteria

1. WHEN an Admin creates an Event, THE System SHALL generate a unique slug and associate the Event with the Admin's user_id
2. THE System SHALL allow each Event to have a name, date, optional passcode, and settings (allow_downloads, retention_days)
3. WHEN an Event is created, THE System SHALL generate a unique guest link in the format https://domain/e/{slug}
4. WHEN an Event is created, THE System SHALL generate a QR code that encodes the guest link
5. THE System SHALL allow an Admin to retrieve all Events filtered by their owner_user_id
6. WHEN an Admin queries Event details, THE System SHALL return only Events they own

### Requirement 3: Photo Upload and Storage

**User Story:** As an Admin, I want to bulk upload photos to a specific Event, so that guests can discover their photos through face recognition.

#### Acceptance Criteria

1. WHEN an Admin uploads photos to an Event, THE Storage_Service SHALL store originals in MinIO at events/{eventId}/original/{imageId}.jpg
2. WHEN a photo is uploaded, THE System SHALL generate a thumbnail at 512px width and store it at events/{eventId}/thumb/{imageId}.jpg
3. WHEN a photo is uploaded, THE System SHALL extract EXIF metadata and store it with the image record
4. THE System SHALL compute a hash of each uploaded photo to detect duplicates within the Event
5. WHEN a photo is uploaded, THE System SHALL create an image record with status 'pending' and event_id
6. THE System SHALL prevent Admins from uploading photos to Events they do not own

### Requirement 4: Face Recognition Indexing

**User Story:** As an Admin, I want uploaded photos to be automatically indexed for face recognition, so that guests can find themselves without manual tagging.

#### Acceptance Criteria

1. WHEN a photo is uploaded with status 'pending', THE Face_Indexer SHALL process it asynchronously using a background worker
2. WHEN processing a photo, THE Face_Indexer SHALL use InsightFace (ArcFace) to detect all faces in the image
3. WHEN a face is detected, THE Face_Indexer SHALL compute a 512-dimensional embedding vector
4. THE Face_Indexer SHALL store each face embedding in the Vector_Database with image_id, bounding box coordinates, and quality score
5. WHEN face indexing completes, THE System SHALL update the image status to 'indexed'
6. WHEN face detection fails or no faces are found, THE System SHALL update the image status to 'no_faces'
7. THE System SHALL ensure all face embeddings are associated with the correct event_id through the image relationship

### Requirement 5: Guest Access and Authentication

**User Story:** As a Guest, I want to access an Event using a unique link or QR code, so that I can scan my face and find my photos.

#### Acceptance Criteria

1. WHEN a Guest visits /e/{slug}, THE System SHALL retrieve the Event by slug and verify it exists
2. WHEN an Event has a passcode, THE System SHALL require the Guest to provide the correct passcode before proceeding
3. WHEN a Guest provides a valid passcode, THE System SHALL verify it using bcrypt comparison
4. WHEN a Guest is authenticated for an Event, THE System SHALL create an Event_Token scoped to that event_id with an expiration time
5. THE System SHALL ensure Event_Tokens cannot be used to access different Events
6. WHEN an Event_Token expires, THE System SHALL require the Guest to re-authenticate

### Requirement 6: Live Face Scanning and Matching

**User Story:** As a Guest, I want to scan my face live using my device camera, so that the system can find photos containing my face from the Event.

#### Acceptance Criteria

1. WHEN a Guest initiates a face scan, THE System SHALL capture 1-3 frames from the device camera using WebRTC
2. WHEN frames are captured, THE System SHALL detect a face in at least one frame and compute its embedding vector
3. WHEN a face embedding is computed, THE System SHALL perform vector similarity search ONLY within faces associated with the current event_id
4. THE System SHALL use cosine similarity or L2 distance to find faces with similarity above a configurable threshold
5. WHEN matching faces are found, THE System SHALL return the associated image records with presigned URLs for viewing
6. THE System SHALL generate presigned URLs with short expiry (15 minutes) for security
7. WHEN no matching faces are found, THE System SHALL return an empty result set with an appropriate message

### Requirement 7: Event-Level Data Isolation

**User Story:** As a system architect, I want complete isolation between Events, so that Guest queries cannot leak photos across different weddings.

#### Acceptance Criteria

1. WHEN a Guest performs a face scan, THE System SHALL filter all face similarity searches by the Event_Token's event_id
2. THE System SHALL ensure no API endpoint allows browsing photos across multiple Events
3. WHEN generating presigned URLs, THE System SHALL validate that the requested image belongs to the Guest's current Event
4. THE System SHALL enforce that Event_Tokens contain event_id and validate it on every Guest request
5. WHEN an Admin queries Event data, THE System SHALL filter by owner_user_id to prevent cross-tenant access

### Requirement 8: Photo Download and Sharing

**User Story:** As a Guest, I want to download photos that match my face, so that I can keep personal copies from the Event.

#### Acceptance Criteria

1. WHEN an Event has allow_downloads enabled, THE System SHALL provide download links for matched photos
2. WHEN a Guest requests a download, THE System SHALL verify the image belongs to their current Event
3. WHEN generating download URLs, THE System SHALL use presigned URLs with appropriate expiry
4. WHEN an Event has allow_downloads disabled, THE System SHALL prevent download requests and return an error
5. THE System SHALL serve original quality images for downloads, not thumbnails

### Requirement 9: Event Status and Monitoring

**User Story:** As an Admin, I want to monitor the indexing status of my Event, so that I know when guests can start scanning.

#### Acceptance Criteria

1. WHEN an Admin requests Event status, THE System SHALL return counts of images by status (pending, indexed, no_faces, failed)
2. THE System SHALL calculate and return the percentage of photos that have been indexed
3. WHEN an Admin requests to reindex an Event, THE System SHALL reset all image statuses to 'pending' and queue them for processing
4. THE System SHALL track the total number of faces detected across all photos in the Event
5. THE System SHALL only return status for Events owned by the requesting Admin

### Requirement 10: Rate Limiting and Security

**User Story:** As a system administrator, I want to prevent abuse of the face scanning feature, so that the system remains available and secure.

#### Acceptance Criteria

1. WHEN a Guest attempts multiple face scans, THE System SHALL enforce a rate limit of 10 scans per Event_Token per hour
2. WHEN rate limits are exceeded, THE System SHALL return a 429 error with retry-after information
3. THE System SHALL log all face scan attempts with event_id, timestamp, and result status
4. WHEN suspicious activity is detected, THE System SHALL create audit log entries for review
5. THE System SHALL validate all file uploads to ensure they are valid image formats (JPEG, PNG)

### Requirement 11: Data Retention and Cleanup

**User Story:** As an Admin, I want to set retention policies for Events, so that storage costs are managed and data privacy is maintained.

#### Acceptance Criteria

1. WHEN an Event is created, THE System SHALL allow setting a retention_days value
2. WHEN an Event exceeds its retention period, THE System SHALL mark it for deletion
3. WHEN an Event is deleted, THE System SHALL remove all associated images from Storage_Service
4. WHEN an Event is deleted, THE System SHALL remove all associated face embeddings from Vector_Database
5. THE System SHALL remove all associated image and face records from the database
6. THE System SHALL create audit log entries for all deletion operations

### Requirement 12: Audit Logging

**User Story:** As an Admin, I want to review access logs for my Events, so that I can monitor Guest activity and troubleshoot issues.

#### Acceptance Criteria

1. WHEN a Guest accesses an Event, THE System SHALL create an audit log entry with event_id, actor_type 'guest', and action 'access'
2. WHEN a Guest performs a face scan, THE System SHALL log the action with metadata including match count
3. WHEN an Admin uploads photos, THE System SHALL log the action with metadata including photo count
4. WHEN an Admin reindexes an Event, THE System SHALL log the action
5. THE System SHALL allow Admins to query audit logs filtered by their event_id
6. THE System SHALL ensure audit logs cannot be accessed across tenant boundaries

### Requirement 13: Scalability and Performance

**User Story:** As a system architect, I want the system to handle typical wedding photo volumes efficiently, so that Admins and Guests have a responsive experience.

#### Acceptance Criteria

1. THE System SHALL support Events with 3,000 to 8,000 photos
2. WHEN performing vector similarity search, THE System SHALL return results within 2 seconds for Events with up to 10,000 faces
3. THE Face_Indexer SHALL process photos at a rate of at least 10 photos per minute per worker
4. THE System SHALL support multiple concurrent Face_Indexer workers for parallel processing
5. WHEN generating thumbnails, THE System SHALL use efficient image processing to minimize CPU usage

### Requirement 14: Deployment and Infrastructure

**User Story:** As a system administrator, I want to deploy the entire stack using open-source tools, so that there are no licensing costs or vendor lock-in.

#### Acceptance Criteria

1. THE System SHALL provide a Docker Compose configuration that deploys all services
2. THE System SHALL use only open-source components: PostgreSQL, MinIO, Redis, FastAPI, Next.js, InsightFace
3. WHEN deployed, THE System SHALL use Caddy or Nginx as a reverse proxy with automatic HTTPS
4. THE System SHALL provide database migration scripts using Alembic
5. THE System SHALL include health check endpoints for all services
6. THE System SHALL provide environment-based configuration for production and development
