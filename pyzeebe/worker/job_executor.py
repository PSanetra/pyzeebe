import asyncio
import logging
from typing import Callable

from pyzeebe.errors import JobAlreadyDeactivatedError
from pyzeebe.job.job import Job, JobController
from pyzeebe.task.task import Task
from pyzeebe.worker.task_state import TaskState

logger = logging.getLogger(__name__)

AsyncTaskCallback = Callable[["asyncio.Future[None]"], None]


class JobExecutor:
    def __init__(self, task: Task, jobs: "asyncio.Queue[Job]", task_state: TaskState, job_controller: JobController):
        self.task = task
        self.jobs = jobs
        self.task_state = task_state
        self.stop_event = asyncio.Event()
        self.job_controller = job_controller

    async def execute(self) -> None:
        while self.should_execute():
            job = await self.get_next_job()
            task = asyncio.create_task(self.execute_one_job(job))
            task.add_done_callback(create_job_callback(self, job))

    async def get_next_job(self) -> Job:
        return await self.jobs.get()

    async def execute_one_job(self, job: Job) -> None:
        try:
            await self.task.job_handler(job, self.job_controller)
        except JobAlreadyDeactivatedError as error:
            logger.warning("Job was already deactivated. Job key: %s", error.job_key)

    def should_execute(self) -> bool:
        return not self.stop_event.is_set()

    async def stop(self) -> None:
        self.stop_event.set()
        await self.jobs.join()


def create_job_callback(job_executor: JobExecutor, job: Job) -> AsyncTaskCallback:
    def callback(_: "asyncio.Future[None]") -> None:
        job_executor.jobs.task_done()
        job_executor.task_state.remove(job)

    return callback
