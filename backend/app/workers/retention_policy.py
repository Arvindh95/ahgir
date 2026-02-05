"""
Retention policy background job for cleaning up expired events
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.database import SessionLocal
from app.models import Event, Image
from app.storage import storage_service
from app.audit import log_action


def check_and_delete_expired_events(db: Session = None):
    """
    Check for expired events and delete them.
    
    This job should be run periodically (e.g., daily) to enforce retention policies.
    Events are considered expired if:
    - created_at + retention_days < current_date
    
    For each expired event:
    1. Log the deletion
    2. Delete all photos from MinIO
    3. Delete the event from database (cascades to all related records)
    
    Args:
        db: Optional database session (for testing). If not provided, creates a new session.
    """
    # Use provided session or create new one
    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()
    
    try:
        # Get current date
        current_date = datetime.utcnow()
        
        # Find all events that have exceeded their retention period
        # Use raw SQL for date arithmetic since SQLAlchemy's func.date() + interval is complex
        expired_events = db.query(Event).filter(
            text("created_at + (retention_days || ' days')::interval < :current_date")
        ).params(current_date=current_date).all()
        
        deleted_count = 0
        
        for event in expired_events:
            try:
                # Get photo count for logging
                photo_count = db.query(func.count(Image.id)).filter(
                    Image.event_id == event.id
                ).scalar() or 0
                
                # Log event deletion
                log_action(
                    db=db,
                    event_id=event.id,
                    actor_type='admin',
                    actor_id=event.owner_user_id,
                    action='delete_event_retention',
                    metadata={
                        'event_name': event.name,
                        'photo_count': photo_count,
                        'retention_days': event.retention_days,
                        'reason': 'retention_policy'
                    }
                )
                
                # Delete all photos from MinIO
                try:
                    storage_service.delete_event_photos(event.id)
                except Exception as e:
                    # Log error but continue with database deletion
                    print(f"Failed to delete photos from MinIO for event {event.id}: {str(e)}")
                
                # Delete event from database (cascades to all related records)
                db.delete(event)
                
                # Only commit if we created the session
                if not db_provided:
                    db.commit()
                else:
                    db.flush()
                
                deleted_count += 1
                print(f"Deleted expired event: {event.name} (ID: {event.id})")
                
            except Exception as e:
                if not db_provided:
                    db.rollback()
                print(f"Failed to delete event {event.id}: {str(e)}")
                continue
        
        print(f"Retention policy job completed. Deleted {deleted_count} expired events.")
        return deleted_count
        
    except Exception as e:
        if not db_provided:
            db.rollback()
        print(f"Retention policy job failed: {str(e)}")
        raise
    finally:
        if not db_provided:
            db.close()


if __name__ == "__main__":
    # Allow running this script directly for testing
    check_and_delete_expired_events()
