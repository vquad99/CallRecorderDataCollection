"""Paged lists: one page of a query and the total, in the same shape for every list endpoint.

`PageNumber` and `PageSize` bound what a caller may ask for: a page far past the end would make
the database skip millions of rows for nothing.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

MAX_PAGE = 10_000

PageNumber = Annotated[int, Query(ge=1, le=MAX_PAGE)]
PageSize = Annotated[int, Query(ge=1, le=100)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


def paginate(
    db: Session,
    query: Select[*tuple[Any, ...]],
    page: int,
    page_size: int,
    *,
    scalars: bool = True,
) -> tuple[list[Any], int]:
    """(rows of the page, total rows) for an ordered query. `scalars=False` keeps whole rows
    (for a query that selects several things)."""
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    paged = query.offset((page - 1) * page_size).limit(page_size)
    items = list(db.scalars(paged).all()) if scalars else list(db.execute(paged).all())
    return items, int(total)
