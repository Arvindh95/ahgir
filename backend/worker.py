"""RQ worker entry point for background job processing."""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rq import Worker
from app.queue import redis_conn, face_indexing_queue

if __name__ == '__main__':
    # Create worker that listens to the face_indexing queue
    worker = Worker([face_indexing_queue], connection=redis_conn)
    
    print("Starting RQ worker for face indexing...")
    print(f"Listening to queue: {face_indexing_queue.name}")
    
    # Start processing jobs
    worker.work()
