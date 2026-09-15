"""Structured research types."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Reliability = Literal["high", "medium", "low"]


class SourceHit(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    reliability: Reliability = "medium"


class ImageHit(BaseModel):
    url: str
    alt: str = ""
    source: str = ""
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None


class VideoHit(BaseModel):
    url: str
    title: str = ""
    thumbnail: str = ""
    duration: str = ""
    source: str = ""


class ExtractedPage(BaseModel):
    url: str
    title: str = ""
    author: str = ""
    published: str = ""
    description: str = ""
    text: str = ""
    images: list[str] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    summary: str
    images: list[ImageHit] = Field(default_factory=list)
    videos: list[VideoHit] = Field(default_factory=list)
    sources: list[SourceHit] = Field(default_factory=list)
    related_queries: list[str] = Field(default_factory=list)
    # For deep research: the sub-queries planned + progress markers
    plan: list[str] = Field(default_factory=list)


class ProgressEvent(BaseModel):
    stage: str            # "planning" | "searching" | "reading" | "synthesizing" | "done"
    message: str
    detail: dict | None = None
