# Testing Face Recognition Locally

Your application is now running with **CompreFace** for face recognition. Here's how to test it:

## Quick Access Links

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **CompreFace Admin**: http://localhost:8082
- **MinIO Console**: http://localhost:9001

## Testing Methods

### Method 1: Automated Test Script

Run the Python test script:

```bash
python test_face_indexing_live.py
```

This will:
1. Check backend health
2. Login as admin (create an account first via frontend)
3. Create a test event
4. Upload a test photo
5. Monitor CompreFace indexing progress

### Method 2: Manual Testing via Frontend

1. **Open Frontend**: http://localhost:3000

2. **Create Admin Account**:
   - Click "Sign Up" or "Register"
   - Use email: `admin@example.com`
   - Use password: `admin123` (or your choice)

3. **Create an Event**:
   - Login with your admin account
   - Click "Create Event"
   - Fill in event details (name, slug, etc.)
   - Enable "Allow Downloads" if you want

4. **Upload Photos**:
   - Go to your event
   - Click "Upload Photos"
   - Upload some photos with faces
   - **Important**: Use real photos with actual faces for best results

5. **Monitor Indexing**:
   - After upload, photos will show as "pending"
   - The worker will process them with CompreFace
   - Status will change to:
     - ✅ "indexed" - Faces detected successfully
     - ⚠️ "no_faces" - No faces found in the photo
     - ❌ "failed" - Processing error

6. **Test Face Scanning** (Guest View):
   - Get the event guest link (e.g., `http://localhost:3000/e/your-event-slug`)
   - Open in incognito/private browser
   - Take a selfie or upload a face photo
   - The system will find matching photos using CompreFace

### Method 3: Manual Testing via API

1. **Check Health**:
```bash
curl http://localhost:8000/health
```

2. **Login** (get your token):
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}'
```

3. **Create Event**:
```bash
curl -X POST http://localhost:8000/events \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "test-event",
    "name": "Test Event",
    "allow_downloads": true,
    "retention_days": 7
  }'
```

4. **Upload Photo**:
```bash
curl -X POST http://localhost:8000/events/EVENT_ID/photos \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@path/to/photo.jpg"
```

5. **Check Event Status**:
```bash
curl http://localhost:8000/events/EVENT_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Monitoring Face Indexing

### Check Worker Logs
```bash
docker-compose logs -f worker
```

You should see:
- `face_indexing: app.workers.face_indexer_compreface.index_photo_compreface(...)`
- `Job OK` when successful

### Check Backend Logs
```bash
docker-compose logs -f backend
```

### Check CompreFace Logs
```bash
docker-compose logs -f compreface-api
docker-compose logs -f compreface-core
```

## Troubleshooting

### Photo stuck in "pending" status?
```bash
# Check worker logs
docker-compose logs worker --tail=50

# Restart worker
docker-compose restart worker
```

### CompreFace not responding?
```bash
# Check if CompreFace is running
docker-compose ps compreface-api compreface-core

# Restart CompreFace
docker-compose restart compreface-api compreface-core
```

### Test CompreFace directly?
```bash
# Visit CompreFace admin panel
open http://localhost:8082

# Test detection API
curl -X POST "http://localhost:8083/api/v1/detection/detect?det_prob_threshold=0.5" \
  -H "x-api-key: 00000000-0000-0000-0000-000000000003" \
  -F "file=@path/to/face_photo.jpg"
```

## What to Expect

### ✅ Success Indicators:
- Photos move from "pending" to "indexed" status
- Worker logs show "Job OK"
- Face count > 0 for photos with faces
- Guest face scanning returns matching photos

### ⚠️ Common Scenarios:
- **No faces detected**: Photo has no recognizable faces
- **Processing time**: 5-30 seconds per photo (depends on photo size)
- **CompreFace startup**: Takes ~1 minute after `docker-compose up`

## Performance Notes

- **Small photos** (< 1MB): ~5-10 seconds
- **Large photos** (> 5MB): ~20-30 seconds
- **Group photos**: Slower (more faces to process)
- **First upload**: Slower (CompreFace model loading)

## Next Steps

After successful testing:
1. Upload real event photos
2. Test guest face scanning
3. Monitor storage usage in MinIO
4. Set up retention policies
5. Configure email notifications

Enjoy your CompreFace-powered face recognition! 🎉
