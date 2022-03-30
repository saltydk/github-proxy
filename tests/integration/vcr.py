import json
import os
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import MutableMapping

from vcr import VCR  # type: ignore

VcrResponse = Mapping[str, MutableMapping[str, Any]]


def is_json_content_type(response: VcrResponse) -> bool:
    for header, values in response["headers"].items():
        if header.lower() == "content-type":
            for value in values:
                if value.lower().startswith("application/json"):
                    return True

    return False


def before_record_response(response: VcrResponse) -> VcrResponse:
    if is_json_content_type(response) and "string" in response["body"]:
        body = json.loads(response["body"]["string"])
        if "token" in body:
            body["token"] = "REDACTED"
            response["body"]["string"] = json.dumps(body).encode()

    return response


filter_headers = [
    "Date",
    ("authorization", "token REDACTED"),
]

vcr = VCR(
    ignore_localhost=True,
    cassette_library_dir=str(Path(__file__).resolve().parent / "fixtures/cassettes"),
    before_record_response=before_record_response,
    filter_headers=filter_headers,
    path_transformer=VCR.ensure_suffix(".yaml"),
    record_mode="none" if os.environ.get("CI") else "once",
    decode_compressed_response=True,
)
