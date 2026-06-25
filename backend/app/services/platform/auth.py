import re

from fastapi import Request


USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def get_user_id(request: Request) -> str:
    user_id = request.headers.get("x-user-id")
    if user_id and USER_ID_PATTERN.fullmatch(user_id):
        return user_id
    return "local-user"
