import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.auth import CurrentUser
from app.services.private_rulebook import (
    MAX_PRIVATE_RULEBOOK_BYTES,
    PrivateRulebookError,
    store_private_rulebook,
)

router = APIRouter(
    prefix="/api/agent/knowledge",
    tags=["Private Knowledge"],
)


@router.post(
    "/private-rulebook",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/pdf": {
                    "schema": {"type": "string", "format": "binary"},
                },
            },
        },
    },
)
async def upload_private_rulebook(
    request: Request,
    current_user: CurrentUser,
    replace: bool = False,
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Content-Type은 application/pdf여야 합니다.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_PRIVATE_RULEBOOK_BYTES:
                raise HTTPException(status_code=413, detail="PDF는 20MB 이하만 업로드할 수 있습니다.")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Content-Length가 올바르지 않습니다.") from error

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PRIVATE_RULEBOOK_BYTES:
            raise HTTPException(status_code=413, detail="PDF는 20MB 이하만 업로드할 수 있습니다.")

    try:
        result = await asyncio.to_thread(
            store_private_rulebook,
            owner_user_id=str(current_user.id),
            pdf_bytes=bytes(body),
            replace=replace,
        )
    except PrivateRulebookError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error

    status_code = 200 if result["unchanged"] or result["replaced"] else 201
    return JSONResponse(status_code=status_code, content=result)
