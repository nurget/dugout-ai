from fastapi import APIRouter

from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
)

router = APIRouter(
    prefix="/api/analysis",
    tags=["Analysis"],
)


@router.post(
    "/preview",
    response_model=AnalysisResponse,
)
async def preview_analysis(
    request: AnalysisRequest,
):
    situation = (
        f"{request.inning}회 "
        f"{request.outs}아웃 "
        f"투구 수 {request.pitch_count}개"
    )

    return AnalysisResponse(
        inning=request.inning,
        outs=request.outs,
        pitch_count=request.pitch_count,
        situation=situation,
        message="경기 상황이 정상적으로 입력되었습니다.",
    )