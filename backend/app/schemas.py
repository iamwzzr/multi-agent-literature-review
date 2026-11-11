from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    workingDirectory: str = Field(min_length=1, max_length=2048)
    knowledgePaths: list[str] = Field(max_length=20)


class Paper(StrictModel):
    id: str
    title: str
    author: str
    year: int | None = Field(default=None, ge=1)
    pages: int = Field(ge=1)
    summary: str = ""
    pdfAvailable: bool = False


class Evidence(StrictModel):
    paper: Paper
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=10000)
    context: str = Field(default="", max_length=5000)


class Section(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    heading: str = Field(min_length=1, max_length=200)
    paragraphs: list[str] = Field(min_length=1, max_length=40)


class ContextTurn(StrictModel):
    question: str = Field(max_length=2000)
    sections: list[Section] = Field(max_length=30)
    evidence: list[Evidence] = Field(max_length=100)
    reply: str | None = Field(default=None, max_length=20000)
    reportUnchanged: bool | None = None


class Reference(StrictModel):
    conversationId: str = Field(min_length=1, max_length=128)
    title: str = Field(max_length=300)
    turn: ContextTurn


class ReviewRequest(StrictModel):
    conversationId: str = Field(min_length=1, max_length=128)
    project: Project
    question: str = Field(min_length=1, max_length=400)
    history: list[ContextTurn] = Field(default_factory=list, max_length=30)
    references: list[Reference] = Field(default_factory=list, max_length=10)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("研究问题不能为空")
        return value.strip()


class ResearchTask(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=600)
    queries: list[str] = Field(min_length=1, max_length=4)


class Plan(StrictModel):
    mode: Literal["review", "reply"] = "review"
    tasks: list[ResearchTask] = Field(min_length=1, max_length=3)


class Finding(StrictModel):
    claim: str = Field(min_length=1, max_length=1600)
    chunk_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2000)
    method: str = Field(default="", max_length=1200)
    limitations: str = Field(default="", max_length=1200)


class Findings(StrictModel):
    findings: list[Finding] = Field(default_factory=list, max_length=8)
    gaps: list[str] = Field(default_factory=list, max_length=8)


class Draft(StrictModel):
    sections: list[Section] = Field(min_length=1, max_length=12)


class Verdict(StrictModel):
    section_id: str
    paragraph: int = Field(ge=0)
    supported: bool
    reason: str = Field(max_length=1500)
    followup_query: str = Field(default="", max_length=600)


class ReviewCheck(StrictModel):
    verdicts: list[Verdict] = Field(max_length=100)


class Reply(StrictModel):
    text: str = Field(min_length=1, max_length=12000)
