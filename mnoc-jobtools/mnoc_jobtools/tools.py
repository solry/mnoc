import json
import logging
import random
import string
from datetime import datetime
from enum import Enum

import redis

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s"
)

QUEUE_NAME_PREFIX = "queue:"  # Used as prefix for Redis list name
AVAILABLE_SYNCJOB_TARGETS = ["device", "db"]
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_HOST = "redis"  # TODO: change to redis

##################################################################


class SyncJobException(Exception):
    """Base exception for Sync Job related exceptions"""

    pass


class SyncJobUnknownTargetException(SyncJobException):
    """Targets for sync must be within AVAILABLE_SYNCJOB_TARGETS"""

    pass


class SyncJobSameTargetsException(SyncJobException):
    """Targets for sync must be different"""

    pass


##################################################################


class RedisJobQueue:
    def __init__(self, host: str = DEFAULT_REDIS_HOST, port: int = DEFAULT_REDIS_PORT):
        self._queue = redis.Redis(host=host, port=port)

    def list(self, queue_name, start: int = 0, end: int = 10):
        return self._queue.lrange(queue_name, start, end)

    def get(self, queue_name: str, block: int = 0):
        return self._queue.blpop([queue_name], block)

    def put(self, queue_name, *values):
        self._queue.rpush(queue_name, *values)


##################################################################


class JobStatus(Enum):
    TODO = "TODO"
    REDO = "REDO"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class SyncJob:
    """
    An instance of this class represents a Job for synchronization
    of device config to DB and vice versa
    """

    JOB_TYPE = "sync"
    QUEUE_NAME = QUEUE_NAME_PREFIX + JOB_TYPE

    def __init__(
        self,
        device_id: int,
        sync_from: str,
        sync_to: str,
        uid: str = None,
        timestamp: datetime = None,
        status: JobStatus = JobStatus.TODO,
        attempts_target: int = 2,
        attempts_done: int = 0,
    ):
        """
        Args:
            device_id: database id of the device to be synced from/to
            sync_from: one of `AVAILABLE_SYNCJOB_TARGETS`. Must differ from sync_to.
                This is the source of configuration data
            sync_to: one of `AVAILABLE_SYNCJOB_TARGETS`. Must differ from sync_from.
                This is the destination, where config will be applied.
            uid (optional): unique identifier for the job.
                Generates automatically when not provided
            timestamp (optional): time when the job submitted to the queue
            status (optional): the status of this Job.
                Determines behaviour of Job handlers (i.e. sync script)
            attempts_target (optional): number of attempts before considering this job failed
            attempts_done (optional): current number of attempts to execute this job
                if it doesn't reach attempts_target, Job can be rescheduled.
        """
        # Sanity checks
        if (
            sync_from not in AVAILABLE_SYNCJOB_TARGETS
            or sync_to not in AVAILABLE_SYNCJOB_TARGETS
        ):
            raise SyncJobUnknownTargetException

        if sync_to == sync_from:
            raise SyncJobSameTargetsException

        self.device_id = device_id
        self.sync_from = sync_from
        self.sync_to = sync_to
        self.uid = self.__generate_uid() if uid is None else uid
        self.timestamp = timestamp
        self.status = status
        self.attempts_target = attempts_target
        self.attempts_done = attempts_done

    def __generate_uid(self):
        """Generates unique ID"""
        return (
            self.JOB_TYPE
            + "-"
            + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        )

    def __serialize_to_json(self):
        """Serializes this instance of class to json-string
        The result can be deserialized into object"""
        return json.dumps(
            {
                "device_id": self.device_id,
                "sync_from": self.sync_from,
                "sync_to": self.sync_to,
                "timestamp": self.timestamp.isoformat(),
                "uid": self.uid,
                "status": self.status.name,
                "attempts_target": self.attempts_target,
                "attempts_done": self.attempts_done,
            }
        )

    def put_to_queue(self):
        """Submits this instance to the RedisJobQueue"""
        job_queue = RedisJobQueue()
        # If no timestamp provided - use the current time
        self.timestamp = self.timestamp if self.timestamp else datetime.now()
        logging.info(f"Submitting sync job to queue: {self}")
        job_queue.put(self.QUEUE_NAME, self.__serialize_to_json())

    @classmethod
    def get_next_from_queue(cls):
        """Retrieve next Job from RedisJobQueue
        This method returns instance of the SyncJob,
        and not payload"""
        job_queue = RedisJobQueue()
        logging.info(f"Retrieving sync job from queue")
        job_data = job_queue.get(cls.QUEUE_NAME)
        job_data = json.loads(job_data[1])
        instance = cls(
            device_id=job_data["device_id"],
            sync_from=job_data["sync_from"],
            sync_to=job_data["sync_to"],
            uid=job_data["uid"],
            timestamp=datetime.fromisoformat(job_data["timestamp"]),
            status=JobStatus[job_data["status"]],
            attempts_target=job_data["attempts_target"],
            attempts_done=job_data["attempts_done"],
        )
        logging.info(f"Job retrieved: {instance}")
        return instance

    def reschedule(self, force: bool = False):
        """
        If you consider this Job unsuccessful,
        you can use this method to reschedule it.
        Job won't be rescheduled if its attempts_done counter hits attempt_target,
        unless you specify force as True
        """

        logging.info(f"Rescheduling sync job {self}")
        if (self.attempts_done < self.attempts_target) or force:
            self.attempts_done += 1
            self.status = JobStatus.REDO
            self.put_to_queue()
            logging.info(f"Sync Job was rescheduled {self}")
        else:
            logging.info(
                f"Sync job attempts have exceeded the limit. Dropping this job: {self}"
            )
            self.status = JobStatus.FAILURE

    def __str__(self):
        return (
            f"<SyncJob> <{self.uid}> {self.sync_from}->{self.sync_to}"
            f" Device: {self.device_id} Status: {self.status}"
        )
