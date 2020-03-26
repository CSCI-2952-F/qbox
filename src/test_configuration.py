import yaml
import unittest
from schema import SchemaError
from unittest.mock import patch, mock_open
from configuration import (
    ROOT_SCHEMA,
    TRANSACTION_SCHEMA,
    HTTP_REQUEST_SCHEMA,
    HTTP_RESPONSE_SCHEMA,
    ConfigurationStore,
    CONFIGURATION_PATH,
)


class TestConfiguration(unittest.TestCase):
    def testValidRequestsSchema(self):

        validRequests = [
            {"method": "GET", "url": "foo"},
            {"method": "POST", "url": "bar"},
            {"method": "PUT", "url": "foobar"},
            {"method": "PATCH", "url": "foo"},
            {"method": "DELETE", "url": "delete"},
            {"method": "HEAD", "url": "delete"},
            {"method": "GET", "url": "bar", "headers": {"example": "yo"}},
            {
                "method": "POST",
                "url": "bar",
                "headers": {"example": "yo"},
                "body": "blahblah",
            },
        ]

        for message in validRequests:
            HTTP_REQUEST_SCHEMA.validate(message)

    def testValidResponseSchema(self):

        validResponses = [
            {"status-code": 200, "url": "foo"},
            {"status-code": 200, "url": "foo", "headers": {"la": "la"}},
            {
                "status-code": 200,
                "url": "foo",
                "headers": {"la": "la"},
                "body": "fangrubber",
            },
        ]

        for message in validResponses:
            HTTP_RESPONSE_SCHEMA.validate(message)

    def testValidTransactionSchema(self):

        validTransaction = {
            "method": "GET",
            "url": "destination",
            "headers": {
                "X-Qbox-Transaction": "1",
                "X-Qbox-Status": "INITIATE-TRANSACTION",
            },
            "onFailure": [
                {
                    "method": "POST",
                    "url": "destination",
                    "headers": {
                        "X-Qbox-Transaction": "1",
                        "X-Qbox-Status": "COMPENSATE-TRANSACTION",
                    },
                    "timeout": 30,
                    "maxRetriesOnTimeout": 300,
                    "isSuccessIfReceives": [{"status-code": 200}],
                }
            ],
            "isSuccessIfReceives": [{"status-code": 200}],
            "timeout": 30,
            "maxRetriesOnTimeout": 3,
        }

        TRANSACTION_SCHEMA.validate(validTransaction)

    def test_valid_root_schema(self):

        validRoot = {
            "host": "me.svc",
            "matchRequest": {
                "method": "GET",
                "url": "qbox.me.svc",
                "headers": {"Hey-Qbox": "Begin-Transaction"},
            },
            "onMatchedRequest": [
                {
                    "method": "POST",
                    "url": "foo.svc",
                    "headers": {"custom": "value"},
                    "onFailure": [
                        {
                            "method": "POST",
                            "url": "foo.svc",
                            "headers": {
                                # Commented out headers are automatically populated by Qbox
                                # and are shown here for demonstration purposes of the final output
                                # "X-Qbox-Transaction": "1"
                                # "X-Qbox-Status": "COMPENSATE-TRANSACTION"
                                # "Hey-Qbox": "Begin-Transaction"
                                # "custom": "value"
                            },
                            "timeout": 30,
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

        ROOT_SCHEMA.validate(validRoot)


class TestConfigurationManager(unittest.TestCase):

    validRoot = {
        "host": "me.svc",
        "matchRequest": {
            "method": "GET",
            "url": "qbox.me.svc",
            "headers": {"Hey-Qbox": "Begin-Transaction"},
        },
        "onMatchedRequest": [
            {
                "method": "POST",
                "url": "foo.svc",
                "headers": {"custom": "value"},
                "onFailure": [
                    {
                        "method": "POST",
                        "url": "foo.svc",
                        "headers": {
                            # Commented out headers are automatically populated by Qbox
                            # and are shown here for demonstration purposes of the final output
                            # "X-Qbox-Transaction": "1"
                            # "X-Qbox-Status": "COMPENSATE-TRANSACTION"
                            # "Hey-Qbox": "Begin-Transaction"
                            # "custom": "value"
                        },
                        "timeout": 30,
                        "isSuccessIfReceives": [{"status-code": 200}],
                    }
                ],
                "isSuccessIfReceives": [{"status-code": 200}],
                "timeout": 30,
                "maxRetriesOnTimeout": 3,
            }
        ],
        "onAllSucceeded": {"status-code": 200},
        "onAnyFailed": {"status-code": 200},
    }

    def test_get_config(self):

        with patch(
            "builtins.open", mock_open(read_data=yaml.dump(self.validRoot))
        ) as mock_file:

            with patch("os.path.exists") as os_mock:
                os_mock.return_value = True
                configuration = ConfigurationStore().get_config()

            mock_file.assert_called_with(CONFIGURATION_PATH)
            self.assertIn("matchRequest", configuration)
            self.assertIn("onMatchedRequest", configuration)
