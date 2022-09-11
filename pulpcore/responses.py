import asyncio

from asgiref.sync import sync_to_async

from aiohttp import hdrs
from aiohttp.web import StreamResponse
from aiohttp.web_exceptions import (
    HTTPPartialContent,
    HTTPRequestRangeNotSatisfiable,
)

from pulpcore.app.models import Artifact


class ArtifactResponse(StreamResponse):
    """A response object can be used to send artifacts."""

    # Heavily borrowed from FileResponse

    def __init__(
        self,
        artifact=None,
        artifact_pk=None,
        chunk_size=256 * 1024,
        status=200,
        reason=None,
        headers=None,
    ):
        assert (artifact is not None) ^ (artifact_pk is not None)

        super().__init__(status=status, reason=reason, headers=headers)

        self._artifact = artifact
        self._artifact_pk = artifact_pk
        self._chunk_size = chunk_size

    async def _sendfile(self, request, fobj, offset, count):
        # To keep memory usage low, fobj is transferred in chunks
        # controlled by the constructor's chunk_size argument.

        writer = await super().prepare(request)
        assert writer is not None

        loop = asyncio.get_event_loop()

        await loop.run_in_executor(None, fobj.seek, offset)

        chunk = await loop.run_in_executor(None, fobj.read, min(self._chunk_size, count))
        while chunk:
            await writer.write(chunk)
            count = count - self._chunk_size
            if count <= 0:
                break
            chunk = await loop.run_in_executor(None, fobj.read, min(self._chunk_size, count))

        await writer.drain()
        return writer

    async def prepare(self, request):
        if self._artifact is None:

            def _get_artifact(pk):
                return Artifact.objects.select_related("pulp_domain").get(pk=pk)

            self._artifact = await sync_to_async(_get_artifact)(self._artifact_pk)

        self._file = self._artifact.file

        loop = asyncio.get_event_loop()

        if hdrs.CONTENT_TYPE not in self.headers:
            self.content_type = "application/octet-stream"

        status = self._status
        file_size = self._file.size
        count = file_size

        start = None

        ifrange = request.if_range
        if ifrange is None:
            try:
                rng = request.http_range
                start = rng.start
                end = rng.stop
            except ValueError:
                # https://tools.ietf.org/html/rfc7233:
                # A server generating a 416 (Range Not Satisfiable) response to
                # a byte-range request SHOULD send a Content-Range header field
                # with an unsatisfied-range value.
                # The complete-length in a 416 response indicates the current
                # length of the selected representation.
                #
                # Will do the same below. Many servers ignore this and do not
                # send a Content-Range header with HTTP 416
                self.headers[hdrs.CONTENT_RANGE] = f"bytes */{file_size}"
                self.set_status(HTTPRequestRangeNotSatisfiable.status_code)
                return await super().prepare(request)

            # If a range request has been made, convert start, end slice
            # notation into file pointer offset and count
            if start is not None or end is not None:
                if start < 0 and end is None:  # return tail of file
                    start += file_size
                    if start < 0:
                        # if Range:bytes=-1000 in request header but file size
                        # is only 200, there would be trouble without this
                        start = 0
                    count = file_size - start
                else:
                    # rfc7233:If the last-byte-pos value is
                    # absent, or if the value is greater than or equal to
                    # the current length of the representatin data,
                    # the byte range is interpreted as the remainder
                    # of the representation (i.e., the server replaces the
                    # value of last-byte-pos with a value that is one less than
                    # the current length of the selected representation).
                    count = min(end if end is not None else file_size, file_size) - start

                if start >= file_size:
                    # HTTP 416 should be returned in this case.
                    #
                    # According to https://tools.ietf.org/html/rfc7233:
                    # If a valid byte-range-set includes at least one
                    # byte-range-spec with a first-byte-pos that is less than
                    # the current length of the representation, or at least one
                    # suffix-byte-range-spec with a non-zero suffix-length,
                    # then the byte-range-set is satisfiable. Otherwise, the
                    # byte-range-set is unsatisfiable.
                    self.headers[hdrs.CONTENT_RANGE] = f"bytes */{file_size}"
                    self.set_status(HTTPRequestRangeNotSatisfiable.status_code)
                    return await super().prepare(request)

                status = HTTPPartialContent.status_code
                # Even though you are sending the whole file, you should still
                # return a HTTP 206 for a Range request.
                self.set_status(status)

        self.content_length = count

        self.headers[hdrs.ACCEPT_RANGES] = "bytes"

        if status == HTTPPartialContent.status_code:
            self.headers[hdrs.CONTENT_RANGE] = "bytes {}-{}/{}".format(
                start, start + count - 1, file_size
            )

        # If we are sending 0 bytes calling sendfile() will throw a ValueError
        if count == 0 or request.method == hdrs.METH_HEAD or self.status in [204, 304]:
            return await super().prepare(request)

        if start:  # be aware that start could be None or int=0 here.
            offset = start
        else:
            offset = 0

        try:
            return await self._sendfile(request, self._file, offset, count)
        finally:
            await loop.run_in_executor(None, self._file.close)
