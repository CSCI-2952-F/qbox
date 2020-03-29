import unittest
import requests_mock
from interpolate import interpolate
from coordinator import SagaCoordinator, RequestNode


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
            "onAllSucceeded": {"status-code": 200},
        }

        with requests_mock.Mocker() as m:
            m.post("http://foo.svc/transact", status_code=200)
            coordinator = SagaCoordinator(configuration)
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
            coordinator = SagaCoordinator(configuration)
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://foo.svc/transact"],
                [request.url for request in m.request_history],
            )
            self.assertFalse(success)
            self.assertEqual(len(transactions), 0)
            self.assertEqual(len(failed_compensations), 0)

    def test_saga_sends_with_resolved_interpolations(self):
        """
        This test checks if the saga coordinator correctly handles inserting interpolating
        message values before they are sent.

        Interpolation semantics can be tricky. 

        Here's a rough guide of what to expect:

            - An interpolation is an expression of the form ${EXPR[:DEFAULT]} inserted into another string. The expression
              will then be evaluated by the coordinator right before sending.

            - An interpolation can only appear in an HTTP_REQUEST_SCHEMA type. It can only appear in the `url`,
              in the values of `header` entries, and in the `body`. 

            - An HTTP_REQUEST_SCHEMA can request the following attributes to be interpolated:

                - For any transaction in `onMatchedRequest`, the headers and body of the `matchRequest`. 
                  Accessed by EXPR set to `parent.headers.<HEADER>` or `parent.body`.

                - In `onFailure`, the headers and body of the transaction request. 
                  Accessed by EXPR set to `parent.headers.<HEADER>` or `parent.body`.

                - In `onFailure`, the headers and body of the transaction response that prompted a failure. 
                  Accessed by EXPR set to `parent.response.headers.<HEADER>` and `parent.response.body`. If the 
                  response does not exist (say, because of timeouts and maxRetriesOnTimeout), an empty string
                  will be inserted. If DEFAULT is specified, then DEFAULT will be inserted.

                -  In `isSuccessIfReceives`, the headers and body of the transaction request. 
                  Accessed by EXPR set to `parent.headers.<HEADER>` or `parent.body`.

                - In `onAllSucceeded`, the responses and requests for each transaction (not compensating transactions).
                  Accessed by EXPR set to `transaction[N].request.headers.<header>`, `transaction[N].request.body`, \
                  `transaction[N].response.headers.<header>` or `transaction[N].response.body`. N here is zero-indexed array index,
                  and refers to the corresponding Nth transaction in `onMatchRequest`.

                - In `onAnyFailed`, the responses and requests for each transaction (not compensating transactions).
                  Accessed by EXPR set to `transaction[N].request.headers.<header>`, `transaction[N].request.body`, \
                  `transaction[N].request.headers.<header>` or `transaction[N].response.body`. N here is zero-indexed array index,
                  and refers to the corresponding Nth transaction in `onMatchRequest`. If any of these transactions were cancelled,
                  the corresponding interpolation string will evalute to an empty string - use DEFAULT instead. 
        """

        configuration = {
            "host": "me.svc",
            "matchRequest": {
                "method": "GET",
                "url": "http://localhost:20000",
                "headers": {"Start-Faking": "True"},
            },
            "onMatchedRequest": [
                {
                    "method": "POST",
                    "url": "http://ratings.svc/add/${parent.headers.PRODUCT-ID}",
                    "headers": {
                        "MY_HEADER": "${parent.headers.PRODUCT-ID}",
                        "MY_OTHER_HEADER": "LIFE",
                    },
                    "isSuccessIfReceives": [{"status-code": 200, "body": "success"}],
                    "onFailure": [
                        {
                            "method": "POST",
                            "url": "http://ratings.svc/delete/${root.headers.PRODUCT-ID}",
                            "headers": {
                                "SHOULD_EXIST": "${parent.headers.MY_OTHER_HEADER}",
                                "SHOULD_NOT_EXIST": "${parent.headers.FOO:laaa}",
                            },
                            "timeout": 3,
                            "maxRetriesOnTimeout": 1,
                            "isSuccessIfReceives": [{"status-code": 200}],
                        }
                    ],
                    "timeout": 30,
                    "maxRetriesOnTimeout": 3,
                }
            ],
            "onAllSucceeded": {"status-code": 200},
            "onAnyFailed": {"status-code": 200},
        }

        start_request_headers = {"PRODUCT-ID": "12"}

        with requests_mock.Mocker() as m:
            m.post("http://ratings.svc/add/12", status_code=200, text="success")
            coordinator = SagaCoordinator(
                configuration, start_request_headers=start_request_headers
            )
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://ratings.svc/add/12"],
                [request.url for request in m.request_history],
            )
            self.assertEqual("12", m.request_history[0].headers["MY_HEADER"])
            self.assertTrue(success)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(len(failed_compensations), 0)

        with requests_mock.Mocker() as m:
            m.post("http://ratings.svc/add/12", status_code=404)
            coordinator = SagaCoordinator(
                configuration, start_request_headers=start_request_headers
            )
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://ratings.svc/add/12"],
                [request.url for request in m.request_history],
            )
            self.assertEqual("12", m.request_history[0].headers["MY_HEADER"])
            self.assertFalse(success)
            self.assertEqual(len(transactions), 0)
            self.assertEqual(len(failed_compensations), 0)

    def test_saga_executes_with_resolved_interpolations_for_real_configuration(self):
        configuration = {
            "host": "productpage.svc",
            "matchRequest": {
                "method": "GET",
                "url": "http://localhost:3001",
                "headers": {"Start-Faking": "True"},
            },
            "onMatchedRequest": [
                {
                    "method": "GET",
                    "url": "http://ratings.svc/add/${parent.headers.Product-Id}",
                    "isSuccessIfReceives": [
                        {
                            "status-code": 200,
                            "headers": {"Content-type": "application/json"},
                        }
                    ],
                    "onFailure": [
                        {
                            "method": "GET",
                            "url": "http://ratings.svc/delete/${root.headers.Product-Id}",
                            "timeout": 3,
                            "maxRetriesOnTimeout": 1,
                            "isSuccessIfReceives": [
                                {
                                    "status-code": 200,
                                    "headers": {"Content-type": "application/json"},
                                }
                            ],
                        }
                    ],
                    "timeout": 30,
                    "maxRetriesOnTimeout": 3,
                },
                {
                    "method": "GET",
                    "url": "http://details.svc/details/add/${root.headers.Product-Id}",
                    "isSuccessIfReceives": [
                        {
                            "status-code": 200,
                            "headers": {"Content-type": "application/json"},
                        }
                    ],
                    "onFailure": [
                        {
                            "method": "GET",
                            "url": "http://details.svc/details/remove/${root.headers.Product-Id}",
                            "timeout": 3,
                            "maxRetriesOnTimeout": 1,
                            "isSuccessIfReceives": [
                                {
                                    "status-code": 200,
                                    "headers": {"Content-type": "application/json"},
                                }
                            ],
                        }
                    ],
                    "timeout": 30,
                    "maxRetriesOnTimeout": 3,
                },
            ],
            "onAllSucceeded": {
                "status-code": 200,
                "body": "Ratings: ${transaction[0].response.body}\nDetails: ${transaction[1].response.body}\n",
            },
            "onAnyFailed": {
                "status-code": 500,
                "body": "Ratings: ${transaction[0].response.body}\nDetails: ${transaction[1].response.body}\n",
            },
        }

        start_request_headers = {"Product-Id": "12"}

        with requests_mock.Mocker() as m:
            m.get(
                "http://ratings.svc/add/12",
                status_code=200,
                headers={"Content-type": "application/json"},
                text="bar",
            )
            m.get(
                "http://details.svc/details/add/12",
                status_code=200,
                headers={"Content-type": "application/json"},
                text="foo",
            )
            coordinator = SagaCoordinator(
                configuration, start_request_headers=start_request_headers
            )
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://ratings.svc/add/12", "http://details.svc/details/add/12"],
                [request.url for request in m.request_history],
            )
            self.assertTrue(success)
            self.assertEqual(len(transactions), 2)
            self.assertEqual(len(failed_compensations), 0)

            context = {
                "parent": RequestNode(),
                "root": coordinator.root,
                "transactions": transactions,
            }

            out = interpolate(configuration["onAllSucceeded"]["body"], **context)
            self.assertEqual("Ratings: bar\nDetails: foo\n", out)

        with requests_mock.Mocker() as m:
            m.get("http://ratings.svc/add/12", status_code=403)
            coordinator = SagaCoordinator(
                configuration, start_request_headers=start_request_headers
            )
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                ["http://ratings.svc/add/12"],
                [request.url for request in m.request_history],
            )
            self.assertFalse(success)
            self.assertEqual(len(transactions), 0)
            self.assertEqual(len(failed_compensations), 0)

        with requests_mock.Mocker() as m:
            m.get(
                "http://ratings.svc/add/12",
                status_code=200,
                headers={"Content-type": "application/json"},
            )
            m.get(
                "http://ratings.svc/delete/12",
                status_code=200,
                headers={"Content-type": "application/json"},
            )
            m.get("http://details.svc/details/add/12", status_code=404)
            coordinator = SagaCoordinator(
                configuration, start_request_headers=start_request_headers
            )
            success, transactions, failed_compensations = coordinator.execute_saga()
            self.assertEqual(
                [
                    "http://ratings.svc/add/12",
                    "http://details.svc/details/add/12",
                    "http://ratings.svc/delete/12",
                ],
                [request.url for request in m.request_history],
            )
            self.assertFalse(success)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(len(failed_compensations), 0)
