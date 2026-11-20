"""Bounded ZIP transport for the web app and native firmware worker."""
import asyncio

from fastapi import HTTPException

MAX_RELEASE_BYTES = 64 * 1024 * 1024
ZIP_TYPE = 'application/zip'


class FirmwareUpload:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def read(self, request):
        if request.headers.get('content-type') != ZIP_TYPE:
            raise HTTPException(415, 'Choose a packaged firmware ZIP.')
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_RELEASE_BYTES:
                raise HTTPException(413, 'Choose a release ZIP up to 64 MB.')
            body.extend(chunk)
        if not body:
            raise HTTPException(400, 'The selected firmware ZIP is empty.')
        return body
