import unittest
import requests_mock
from coordinator import SagaCoordinator


class TestSagaCoordinator(unittest.TestCase):
    def test_saga_sends(self):

        configuration = {
            "host": "me.svc",
            "matchRequest": {
                "method": "GET",
                "url": "qbox.me.svc",
                "headers": {"Hey-Qbox": "Begin-Transaction"},
            },
            "onMatchedRequest": [
                {
                    "method": "POST",
                    "url": "http://foo.svc/transact",
                    "headers": {"custom": "value"},
                    "onFailure": [
                        {
                            "method": "POST",
                            "url": "http://foo.svc/fail",
                            "headers": {},
                            "timeout": 3,
                            "maxRetriesOnTimeout": 1,
                            "isSuccessIfReceives": [{"status-code": 200}],
                        }
                    ],
                    "isSuccessIfReceives": [{"status-code": 200}],
                    "timeout": 30,
                    "maxRetriesOnTimeout": 3,
                }
            ],
            "onAllSucceeded": {"method": "GET", "url": "me.svc"},
        }

        coordinator = SagaCoordinator(configuration)

        with requests_mock.Mocker() as m:
            m.post("http://foo.svc/transact", status_code=200)
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://foo.svc/transact"],
                [request.url for request in m.request_history],
            )
            self.assertTrue(success)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(len(failed_compensations), 0)

        with requests_mock.Mocker() as m:
            m.post("http://foo.svc/transact", status_code=404)
            m.post("http://foo.svc/fail", status_code=200)
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://foo.svc/transact", "http://foo.svc/fail"],
                [request.url for request in m.request_history],
            )
            self.assertFalse(success)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(len(failed_compensations), 0)

        with requests_mock.Mocker() as m:
            m.post("http://foo.svc/transact", status_code=404)
            m.post("http://foo.svc/fail", status_code=403)
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://foo.svc/transact", "http://foo.svc/fail"],
                [request.url for request in m.request_history],
            )
            self.assertFalse(success)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(len(failed_compensations), 1)
