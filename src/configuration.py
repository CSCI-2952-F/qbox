""" 
This file defines the structure of the configuration Qbox uses. 

We perform schema validation for the entire configuration. This is 
basically the power of protobufs without needing to use protobufs. We
use the schema library (https://github.com/keleshev/schema) for this.

See configuration_test.py for example configurations.
"""
import re
import os
import yaml
from interpolate import interpolate
from schema import Schema, And, Or, Optional, Const

CONFIGURATION_PATH = "configuration/config.yaml"

# All messages need to have a source address and a destination address.
# These addresses should resolve using cluster DNS.
# Messages may optionally include a list of headers as string key/value pairs.
# and an optional body. How these headers and bodies are included in new values
# is dependent on where the message is defined in the schema - `matchRequest` messages
# have different behaviour than `onFailue` messages.
HTTP_REQUEST_SCHEMA = Schema(
    {
        "method": lambda t: t in ["GET", "HEAD", "PUT", "PATCH", "DELETE", "POST"],
        "url": str,
        Optional("headers"): Schema(Or({str: str}, {})),
        Optional("body"): str,
    },
    ignore_extra_keys=True,
)

HTTP_RESPONSE_SCHEMA = Schema(
    {
        "status-code": int,
        Optional("headers"): Schema(Or({str: str}, {})),
        Optional("body"): str,
    },
    ignore_extra_keys=True,
)

# Some messages are part of a transaction. Such transactions need to specify a timeout,
# a number of times to retry on a timeout, and a compensating transaction (marked in "onFailure").
#
# Messages in `onFailure` will always inherit headers/bodies from their parent message - if headers
# and bodies are specified under `onFailure`, then headers will be upserted and bodies will be
# overwritten.
#
# Messages in `matchSuccessRequest` are what responses are compared to to mark the transaction
# as succeeded. Any response that does not match that criteria is automatic grounds for the
# transaction as a whole to fail.

COMPENSATING_TRANSACTION_SCHEMA = And(
    Const(
        HTTP_REQUEST_SCHEMA,
        Schema(
            {
                "timeout": And(int, lambda timeout: timeout >= 0),
                Optional("maxRetriesOnTimeout"): And(
                    int, lambda maxRetries: maxRetries >= 0
                ),
                "isSuccessIfReceives": Schema([HTTP_RESPONSE_SCHEMA]),
            },
            ignore_extra_keys=True,
        ),
    ),
)

TRANSACTION_SCHEMA = And(
    Const(
        HTTP_REQUEST_SCHEMA,
        Schema(
            {
                "timeout": And(int, lambda timeout: timeout >= 0),
                Optional("maxRetriesOnTimeout"): And(
                    int, lambda maxRetries: maxRetries >= 0
                ),
                "onFailure": Schema([COMPENSATING_TRANSACTION_SCHEMA]),
                "isSuccessIfReceives": Schema([HTTP_RESPONSE_SCHEMA]),
            },
            ignore_extra_keys=True,
        ),
    ),
)

# The root of our configuration. The list of headers, bodies, etc. supplied in `matchRequest`
# will be used to match the request to initiate the saga workflow.
ROOT_SCHEMA = Schema(
    {
        "host": str,
        "matchRequest": HTTP_REQUEST_SCHEMA,
        "onMatchedRequest": Schema([TRANSACTION_SCHEMA]),
        Optional("onAllSucceeded"): HTTP_RESPONSE_SCHEMA,
        Optional("onAnyFailed"): HTTP_RESPONSE_SCHEMA,
    },
    ignore_extra_keys=True,
)


class ConfigurationStore(object):
    """
    This manager pulls configuration artifacts from a mounted directory called `configuration`.
    The directory mounting in production is handled by Kubernetes ConfigMaps. 
    """

    def __init__(self):

        self.config = []

        if os.path.exists(CONFIGURATION_PATH):
            with open(CONFIGURATION_PATH) as config:
                for c in yaml.safe_load_all(config):
                    self.config.append(ROOT_SCHEMA.validate(c))

    def get_config(self):
        return self.config
