"""Measure sequential downloads from one HTTP or HTTPS URL."""

import argparse
import sys
from http.client import HTTPException
from time import perf_counter
from typing import TextIO
from urllib.parse import urlsplit
from urllib.request import urlopen


REQUEST_COUNT = 10
READ_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30
BYTES_PER_MIB = 1024 * 1024
PROGRESS_INTERVAL_SECONDS = 0.2


class DownloadProgress:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.interactive = stream.isatty()
        self.request_number = 0
        self.line_width = 0
        self.next_update = float("-inf")

    def start(self, request_number: int) -> None:
        self.request_number = request_number
        self.next_update = float("-inf")
        self._show_request("waiting for response")

    def received(self, downloaded: int, expected: int | None) -> None:
        if not self.interactive:
            return
        now = perf_counter()
        if now < self.next_update:
            return
        self.next_update = now + PROGRESS_INTERVAL_SECONDS

        size = f"{downloaded:,} bytes"
        if expected is not None and expected > 0:
            percent = downloaded * 100 // expected
            size = f"{downloaded:,}/{expected:,} bytes ({percent}%)"
        self._show_request(size)

    def finish(self) -> None:
        self._render(REQUEST_COUNT, f"{REQUEST_COUNT}/{REQUEST_COUNT} downloads complete")
        self.end_line()

    def end_line(self) -> None:
        if self.interactive:
            print(file=self.stream, flush=True)

    def _show_request(self, detail: str) -> None:
        self._render(self.request_number - 1, f"Request {self.request_number}/{REQUEST_COUNT} | {detail}")

    def _render(self, completed: int, detail: str) -> None:
        bar = "#" * completed + "-" * (REQUEST_COUNT - completed)
        line = f"[{bar}] {detail}"
        if self.interactive:
            self.stream.write("\r" + line.ljust(self.line_width))
            self.line_width = len(line)
        else:
            self.stream.write(line + "\n")
        self.stream.flush()


def download(url: str, progress: DownloadProgress) -> tuple[int, float]:
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

        while chunk := response.read1(READ_SIZE):
            downloaded += len(chunk)
            progress.received(downloaded, expected)
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
    progress = DownloadProgress(sys.stderr)
    for request_number in range(1, REQUEST_COUNT + 1):
        progress.start(request_number)
        try:
            downloaded, elapsed = download(args.url, progress)
        except (OSError, HTTPException, ValueError) as error:
            progress.end_line()
            print(f"Request {request_number}/{REQUEST_COUNT} failed: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            progress.end_line()
            print("Benchmark interrupted.", file=sys.stderr)
            return 130
        total_bytes += downloaded
        total_seconds += elapsed

    progress.finish()
    print(f"Average request time: {total_seconds / REQUEST_COUNT:.6f} s")
    print(f"Total downloaded: {total_bytes} bytes")
    print(f"Download speed: {total_bytes / BYTES_PER_MIB / total_seconds:.3f} MiB/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
