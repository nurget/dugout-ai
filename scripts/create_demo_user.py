import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User


TEAM_CODES = {
    "KIA", "SS", "LG", "KT", "SSG",
    "NC", "OB", "LT", "HH", "WO",
}

ROLES = {"MANAGER", "COACH"}


async def create_user(
    username: str,
    password: str,
    team_code: str,
    role: str,
) -> None:
    if team_code not in TEAM_CODES:
        raise ValueError("지원하지 않는 구단 코드입니다.")

    if role not in ROLES:
        raise ValueError("지원하지 않는 역할입니다.")

    if len(password) < 12:
        raise ValueError("비밀번호는 12자 이상이어야 합니다.")

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(User).where(
                User.username == username
            )
        )

        if existing is not None:
            raise ValueError("이미 존재하는 아이디입니다.")

        session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                team_code=team_code,
                role=role,
            )
        )

        await session.commit()

    print(
        f"계정 생성 완료: {username} "
        f"({team_code} / {role})"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--team",
        choices=sorted(TEAM_CODES),
        required=True,
    )
    parser.add_argument(
        "--role",
        choices=sorted(ROLES),
        required=True,
    )

    args = parser.parse_args()

    password = getpass("비밀번호: ")
    confirm = getpass("비밀번호 확인: ")

    if password != confirm:
        parser.error("비밀번호가 일치하지 않습니다.")

    asyncio.run(
        create_user(
            username=args.username,
            password=password,
            team_code=args.team,
            role=args.role,
        )
    )


if __name__ == "__main__":
    main()