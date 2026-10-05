import os
import sys
import redis
from rq import Worker, Queue, Connection

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

def main() -> None:
    """Run the RQ worker."""
    try:
        conn = redis.from_url(redis_url)
        with Connection(conn):
            worker = Worker(map(Queue, ["default"]))
            print("RQ worker starting up...")
            worker.work()
    except Exception as e:
        print(f"Error starting RQ worker: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
