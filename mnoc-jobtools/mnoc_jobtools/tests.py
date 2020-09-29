import pytest
from mnoc_jobtools.tools import (
    RedisJobQueue,
    SyncJob,
    SyncJobSameTargetsException,
    SyncJobUnknownTargetException, JobStatus,
)
from pytest import fixture


TEST_QUEUE_NAME = "test-queue"


class TestRedisJobQueue:
    def test_class_init(self):
        assert RedisJobQueue()

    def test_put_get(self):
        queue = RedisJobQueue()
        queue._queue.delete(TEST_QUEUE_NAME)
        queue.put(TEST_QUEUE_NAME, "test-value")
        assert queue.get(TEST_QUEUE_NAME)[1].decode() == "test-value"

    def test_put_list(self):
        queue = RedisJobQueue()
        queue._queue.delete(TEST_QUEUE_NAME)
        queue.put(TEST_QUEUE_NAME, "test-value")
        assert queue.list(TEST_QUEUE_NAME) == [b"test-value"]
        queue._queue.delete(TEST_QUEUE_NAME)


@fixture(params=[["db", "device"], ["device", "db"]])
def sync_job(request):
    queue = RedisJobQueue()
    queue._queue.delete(TEST_QUEUE_NAME)
    SyncJob.QUEUE_NAME = TEST_QUEUE_NAME
    yield SyncJob(device_id=1, sync_from=request.param[0], sync_to=request.param[1])
    queue._queue.delete(TEST_QUEUE_NAME)


class TestSyncJob:
    def test_init(self, sync_job):
        assert sync_job

    @pytest.mark.parametrize(
        "sync_from, sync_to",
        [
            pytest.param(
                "db", "db", marks=pytest.mark.xfail(raises=SyncJobSameTargetsException)
            ),
            pytest.param(
                "device",
                "cisco",
                marks=pytest.mark.xfail(raises=SyncJobUnknownTargetException),
            ),
        ],
    )
    def test_init_failure_target(self, sync_from, sync_to):
        SyncJob(1, sync_from=sync_from, sync_to=sync_to)

    def test_ser_des(self, sync_job):
        sync_job.put_to_queue()
        job_from_queue = sync_job.get_next_from_queue()
        assert sync_job.__dict__ == job_from_queue.__dict__

    def test_reschedule(self, sync_job):
        sync_job.reschedule()
        SyncJob.QUEUE_NAME = TEST_QUEUE_NAME
        job_from_queue = SyncJob.get_next_from_queue()
        assert sync_job.attempts_done == 1
        assert job_from_queue.attempts_done == 1
        assert sync_job.status == JobStatus.REDO
        assert job_from_queue.status == JobStatus.REDO

    def test_reschedule_failure(self, sync_job):
        sync_job.attempts_done = 2
        sync_job.reschedule()
        assert sync_job.status == JobStatus.FAILURE
        # Check that the queue is empty:
        assert RedisJobQueue().list(TEST_QUEUE_NAME) == []
