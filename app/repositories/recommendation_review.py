from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation_review import RecommendationReview


async def get_recommendation_review(
    session: AsyncSession,
    *,
    run_id: str,
    reviewer_user_id: str,
) -> RecommendationReview | None:
    return await session.scalar(
        select(RecommendationReview).where(
            RecommendationReview.run_id == run_id,
            RecommendationReview.reviewer_user_id == reviewer_user_id,
        )
    )


async def upsert_recommendation_review(
    session: AsyncSession,
    *,
    run_id: str,
    reviewer_user_id: str,
    team_code: str,
    as_of_date: date,
    outcome: str,
    acceptable_candidate_ids: list[str],
    recommendation_snapshot: dict,
    data_snapshot_ids: dict | None,
) -> RecommendationReview:
    review = await get_recommendation_review(
        session,
        run_id=run_id,
        reviewer_user_id=reviewer_user_id,
    )
    if review is None:
        review = RecommendationReview(
            run_id=run_id,
            reviewer_user_id=reviewer_user_id,
            team_code=team_code,
            as_of_date=as_of_date,
            outcome=outcome,
            acceptable_candidate_ids=acceptable_candidate_ids,
            recommendation_snapshot=recommendation_snapshot,
            data_snapshot_ids=data_snapshot_ids,
        )
        session.add(review)
    else:
        review.team_code = team_code
        review.as_of_date = as_of_date
        review.outcome = outcome
        review.acceptable_candidate_ids = acceptable_candidate_ids
        review.recommendation_snapshot = recommendation_snapshot
        review.data_snapshot_ids = data_snapshot_ids
        review.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(review)
    return review
