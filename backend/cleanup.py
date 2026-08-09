"""만료된 임시 파일/작업을 주기적으로 정리하는 백그라운드 루프."""
import os
import json
import time
import shutil
import asyncio
import logging

from state import SHARED_DIR, JOB_AUDIO_DIR, text_storage, jobs, drop_expired_rate_buckets

logger = logging.getLogger(__name__)


async def cleanup_expired_files_loop():
    while True:
        try:
            now = time.time()
            # 1. Clean memory text storage (older than 30 minutes)
            expired_keys = []
            for key, data in text_storage.items():
                created_at = data.get("created_at", 0)
                if now - created_at > 1800:
                    expired_keys.append(key)
            for key in expired_keys:
                text_storage.pop(key, None)

            # 2. Clean shared audiobooks (older than 24 hours)
            if os.path.exists(SHARED_DIR):
                for share_id in os.listdir(SHARED_DIR):
                    share_dir = os.path.join(SHARED_DIR, share_id)
                    meta_path = os.path.join(share_dir, "meta.json")
                    if os.path.isdir(share_dir) and os.path.exists(meta_path):
                        try:
                            with open(meta_path, "r") as f:
                                meta = json.load(f)
                            if now - meta.get("created_at", 0) > 86400:  # 24 hours
                                shutil.rmtree(share_dir)
                                logger.info("Cleaned expired share share_id=%s", share_id)
                        except Exception as error:
                            # 이 공유 하나를 못 지워도 나머지 정리는 계속해야 한다.
                            # 다만 조용히 넘기지는 않는다 — 같은 항목이 매번
                            # 실패하고 있다면 디스크가 계속 차고 있다는 뜻이다.
                            logger.warning(
                                "Failed to clean share share_id=%s error_type=%s",
                                share_id, type(error).__name__,
                            )

            # 3. 클라이언트가 받아가지 않은 job 오디오 정리 (30분 경과)
            for jid in [k for k, v in jobs.items()
                        if now - v.get("created_at", now) > 1800]:
                job = jobs.pop(jid, None)
                if job and job.get("audio_path"):
                    try:
                        os.remove(job["audio_path"])
                    except OSError:
                        pass
                logger.info("Cleaned expired job job_id=%s", jid)

            # 4. 요청 제한 버킷 — IP마다 항목이 생기고 지워지는 자리가 없었다
            drop_expired_rate_buckets(now)

            # 고아 파일(서버 재시작 등으로 jobs에 없는 파일)도 정리
            if os.path.exists(JOB_AUDIO_DIR):
                for fname in os.listdir(JOB_AUDIO_DIR):
                    fpath = os.path.join(JOB_AUDIO_DIR, fname)
                    try:
                        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 1800:
                            os.remove(fpath)
                    except OSError:
                        pass
        except Exception as e:
            logger.exception("Cleanup background task failed: %s", e)

        await asyncio.sleep(600)  # Every 10 minutes
