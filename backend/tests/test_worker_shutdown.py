import unittest
from unittest.mock import patch

from app.modules.try_on.worker import worker


class WorkerShutdownTests(unittest.TestCase):
    def test_shutdown_finishes_claimed_job_without_claiming_another(self):
        stopping = False
        job = {'id': 'example'}

        def finish_job(claimed_job):
            nonlocal stopping
            self.assertEqual(claimed_job, job)
            stopping = True

        with (
            patch('app.modules.bookings.service.cleanup_booking_holds'),
            patch('app.modules.try_on.worker.cleanup_results'),
            patch('app.modules.try_on.worker.connect') as connect,
            patch('app.modules.try_on.worker.process_job', side_effect=finish_job) as process,
            patch('app.modules.try_on.worker.time.sleep') as sleep,
        ):
            connection = connect.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = job

            worker(stop_requested=lambda: stopping)

        connect.assert_called_once_with()
        process.assert_called_once_with(job)
        sleep.assert_not_called()
