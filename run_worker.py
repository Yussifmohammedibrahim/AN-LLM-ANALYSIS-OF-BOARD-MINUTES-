import os
import sys
import logging
import logging.config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from app.ai_routes import _get_rq_queue


if __name__ == '__main__':
    if load_dotenv is not None:
        load_dotenv(os.path.join(os.path.dirname(__file__), 'itds_env', '.env'))

    logging.config.fileConfig('itds_env/app/logging.conf', disable_existing_loggers=False)

    try:
        from rq import Worker, SimpleWorker
        from rq.timeouts import TimerDeathPenalty
    except Exception as exc:
        message = str(exc)
        if "cannot find context for 'fork'" in message.lower():
            print("RQ import failed on this Python environment (Windows fork context error).")
            print("Use the project virtual environment and reinstall requirements:")
            print("  .\\itds_env\\Scripts\\python.exe -m pip install -r requirements.txt")
            print("  .\\itds_env\\Scripts\\python.exe run_worker.py")
        else:
            print(f'RQ worker could not start: failed to import rq Worker: {exc}')
        sys.exit(1)

    queue = _get_rq_queue()
    if queue is None:
        print('RQ worker could not start: Redis queue unavailable. Check REDIS_URL and Redis server.')
        sys.exit(1)

    print('Starting RQ worker for queue: batch-analysis')
    # Worker uses blocking Redis reads; avoid short socket timeouts from API health-check connections.
    redis_url = os.getenv('REDIS_URL', '').strip()
    worker_connection = queue.connection
    if redis_url:
        try:
            from redis import Redis
            worker_connection = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=None)
        except Exception:
            pass

    # Windows cannot use fork-based workers; SimpleWorker runs jobs in-process.
    worker_cls = SimpleWorker if os.name == 'nt' else Worker
    if worker_cls is SimpleWorker:
        print('Windows detected: using RQ SimpleWorker (no fork).')

    if worker_cls is SimpleWorker:
        class WindowsSimpleWorker(SimpleWorker):
            death_penalty_class = TimerDeathPenalty

        worker = WindowsSimpleWorker([queue], connection=worker_connection)
    else:
        worker = worker_cls([queue], connection=worker_connection)
    worker.work(with_scheduler=False)
