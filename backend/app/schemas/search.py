from typing import Optional

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    entity_type: str
    id: int
    title: str
    subtitle: Optional[str] = None
    parent_id: Optional[int] = None


class SearchResponse(BaseModel):
    query: str
    results: dict[str, list[SearchResultItem]]
    total: int
