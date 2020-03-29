import re


def interpolate(line, parent, root, transactions):
    """
    Replace an interpolation pattern with the corresponding values.
    """

    if not line:
        return line

    def replace_root_headers(match):
        header, default = match.groups()
        return root.headers.get(header, default)

    def replace_root_body(match):
        default = match.group("default")
        return root.body if root.body else default

    def replace_parent_headers(match):
        header, default = match.groups()
        return parent.headers.get(header, default)

    def replace_parent_response_headers(match):
        header, default = match.groups()
        return parent.response_headers.get(header, default)

    def replace_parent_response_body(match):
        default = match.groups("default")
        return parent.response_body if parent.response_body else default

    def replace_parent_body(match):
        default = match.groups("default")
        return parent.body if parent.body else default

    def replace_transaction_request_headers(match):
        index, header, default = match.groups()
        index = int(index)

        if 0 <= index < len(transactions):
            return (
                transactions[index]
                .get("request", {})
                .get("headers", {})
                .get(header, default)
            )
        else:
            return default

    def replace_transaction_response_headers(match):
        index, header, default = match.groups()
        index = int(index)

        if 0 <= index < len(transactions):
            return transactions[index].response_headers.get(header, default)
        else:
            return default

    def replace_transaction_request_body(match):
        index, default = match.groups()
        index = int(index)

        if 0 <= index < len(transactions):
            body = transactions[index].body
            return default if not body else body
        else:
            return default

    def replace_transaction_response_body(match):
        index, default = match.groups()
        index = int(index)

        if 0 <= index < len(transactions):
            body = transactions[index].response_body
            return default if not body else body
        else:
            return default

    patterns = {
        r"\$\{root\.headers\.(?P<header>[A-Za-z0-9\_\-]+):?(?P<default>.*?)\}": replace_root_headers,
        r"\$\{root\.body:?(?P<default>.*?)\}": replace_root_body,
        r"\$\{parent\.headers\.(?P<header>[A-Za-z0-9\_\-]+):?(?P<default>.*?)\}": replace_parent_headers,
        r"\$\{parent\.body:?(?P<default>.*?)\}": replace_parent_body,
        r"\$\{parent\.response\.headers\.(?P<header>[A-Za-z0-9\_\-]+):?(?P<default>.*?)\}": replace_parent_response_headers,
        r"\$\{parent\.response\.body:?(?P<default>.*?)\}": replace_parent_response_body,
        r"\$\{transaction\[(?P<index>[0-9]+)\]\.request\.headers\.(?P<header>[A-Za-z0-9\_\-]+):?(?P<default>.*?)\}": replace_transaction_request_headers,
        r"\$\{transaction\[(?P<index>[0-9]+)\]\.response\.headers\.(?P<header>[A-Za-z0-9\_\-]+):?(?P<default>.*?)\}": replace_transaction_response_headers,
        r"\$\{transaction\[(?P<index>[0-9]+)\]\.request\.body:?(?P<default>.*?)\}": replace_transaction_request_body,
        r"\$\{transaction\[(?P<index>[0-9]+)\]\.response\.body:?(?P<default>.*?)\}": replace_transaction_response_body,
    }

    for pattern, replacement_function in patterns.items():
        line = re.sub(pattern, replacement_function, line, flags=re.IGNORECASE)

    return line
