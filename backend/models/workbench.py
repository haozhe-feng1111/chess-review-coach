"""Requests for interactive analysis. Engine scores always use White's perspective."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SearchSettings(BaseModel):
    mode: Literal["time", "depth", "infinite"] = "time"
    seconds: float = Field(default=5, ge=0.1, le=600)
    depth: int = Field(default=20, ge=1, le=60)
    threads: int = Field(default=2, ge=1, le=64)
    hash_mb: int = Field(default=64, ge=16, le=4096)
    multipv: int = Field(default=3, ge=1, le=5)


class StartSearch(BaseModel):
    client_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    sequence: int = Field(ge=1)
    root_fen: str = Field(max_length=128)
    moves: List[str] = Field(default_factory=list, max_length=2000)
    settings: SearchSettings = Field(default_factory=SearchSettings)


class StudyMove(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    parent_id: str = Field(min_length=1, max_length=80)
    uci: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")


class SaveStudy(BaseModel):
    revision: int = Field(ge=0)
    moves: List[StudyMove] = Field(max_length=2000)
    selected_id: str = Field(default="root", max_length=80)
