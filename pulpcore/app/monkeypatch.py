import sys

# This is a monkeypatch for https://github.com/pulp/pulpcore/issues/3869
if sys.version_info.major == 3 and sys.version_info.minor < 12:
    # Code copied from the Python 3.12 standard library
    # We modify the default gzip compression level for writing streams from
    # 9 to 1, attempting to vendor the minimum amount of code.
    # -------------------------------------------------------------------
    # tarfile.py
    # -------------------------------------------------------------------
    # Copyright (C) 2002 Lars Gustaebel <lars@gustaebel.de>
    # All rights reserved.
    #
    # Permission  is  hereby granted,  free  of charge,  to  any person
    # obtaining a  copy of  this software  and associated documentation
    # files  (the  "Software"),  to   deal  in  the  Software   without
    # restriction,  including  without limitation  the  rights to  use,
    # copy, modify, merge, publish, distribute, sublicense, and/or sell
    # copies  of  the  Software,  and to  permit  persons  to  whom the
    # Software  is  furnished  to  do  so,  subject  to  the  following
    # conditions:
    #
    # The above copyright  notice and this  permission notice shall  be
    # included in all copies or substantial portions of the Software.
    #
    # THE SOFTWARE IS PROVIDED "AS  IS", WITHOUT WARRANTY OF ANY  KIND,
    # EXPRESS OR IMPLIED, INCLUDING  BUT NOT LIMITED TO  THE WARRANTIES
    # OF  MERCHANTABILITY,  FITNESS   FOR  A  PARTICULAR   PURPOSE  AND
    # NONINFRINGEMENT.  IN  NO  EVENT SHALL  THE  AUTHORS  OR COPYRIGHT
    # HOLDERS  BE LIABLE  FOR ANY  CLAIM, DAMAGES  OR OTHER  LIABILITY,
    # WHETHER  IN AN  ACTION OF  CONTRACT, TORT  OR OTHERWISE,  ARISING
    # FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    # OTHER DEALINGS IN THE SOFTWARE.

    import tarfile
    from tarfile import NUL
    import struct
    import os
    import time

    class _Stream(tarfile._Stream):
        """Class that serves as an adapter between TarFile and
        a stream-like object.  The stream-like object only
        needs to have a read() or write() method and is accessed
        blockwise.  Use of gzip or bzip2 compression is possible.
        A stream-like object could be for example: sys.stdin,
        sys.stdout, a socket, a tape device etc.

        _Stream is intended to be used only internally.
        """

        def _init_write_gz(self):
            """Initialize for writing with gzip compression."""
            self.cmp = self.zlib.compressobj(
                1, self.zlib.DEFLATED, -self.zlib.MAX_WBITS, self.zlib.DEF_MEM_LEVEL, 0
            )
            timestamp = struct.pack("<L", int(time.time()))
            self.__write(b"\037\213\010\010" + timestamp + b"\002\377")
            if self.name.endswith(".gz"):
                self.name = self.name[:-3]
            # Honor "directory components removed" from RFC1952
            self.name = os.path.basename(self.name)
            # RFC1952 says we must use ISO-8859-1 for the FNAME field.
            self.__write(self.name.encode("iso-8859-1", "replace") + NUL)

    tarfile._Stream = _Stream
