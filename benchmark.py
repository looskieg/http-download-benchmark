"""Measure sequential downloads from one HTTP or HTTPS URL."""

import argparse
import sys
from http.client import HTTPException
from time import perf_counter
from urllib.parse import urlsplit
from urllib.request import urlopen


REQUEST_COUNT = 10
READ_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30
BYTES_PER_MIB = 1024 * 1024


def download(url: str) -> tuple[int, float]:
    started_at = perf_counter()
    downloaded = 0

    with urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        status = response.getcode()
        if status is None or not 200 <= status < 300:
            raise OSError("expected a successful HTTP response")

        expected = None
        lengths = response.headers.get_all("Content-Length", [])
        if lengths and "Transfer-Encoding" not in response.headers:
            expected = int(lengths[0])
            if any(int(length) != expected for length in lengths[1:]):
                raise OSError("conflicting Content-Length headers")

        while chunk := response.read(READ_SIZE):
            downloaded += len(chunk)
        elapsed = perf_counter() - started_at

        # A bounded read can return EOF early for a response with Content-Length.
        if expected is not None and downloaded != expected:
            raise OSError(f"incomplete response: received {downloaded} of {expected} bytes")

    return downloaded, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="HTTP or HTTPS URL to download")
    args = parser.parse_args()

    try:
        url = urlsplit(args.url)
        if url.scheme not in ("http", "https") or not url.hostname:
            parser.error("url must be an HTTP or HTTPS URL with a hostname")
    except ValueError as error:
        parser.error(f"invalid URL: {error}")

    total_bytes = 0
    total_seconds = 0.0
    for request_number in range(1, REQUEST_COUNT + 1):
        try:
            downloaded, elapsed = download(args.url)
        except (OSError, HTTPException, ValueError) as error:
            print(f"Request {request_number}/{REQUEST_COUNT} failed: {error}", file=sys.stderr)
            return 1
        total_bytes += downloaded
        total_seconds += elapsed

    print(f"Average request time: {total_seconds / REQUEST_COUNT:.6f} s")
    print(f"Total downloaded: {total_bytes} bytes")
    print(f"Download speed: {total_bytes / BYTES_PER_MIB / total_seconds:.3f} MiB/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
