"""ORM models. JSON fields are stored as JSON-encoded Text for portability."""
import json

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from .db import Base


class Profile(Base):
    """The single candidate profile (row id=1). `data` holds the parsed,
    user-correctable structured resume as JSON."""
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String, default="")
    data = Column(Text, default="{}")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    dedupe_key = Column(String, unique=True, index=True)
    title = Column(String, nullable=False)
    company = Column(String, default="")
    location = Column(String, default="")
    job_type = Column(String, default="")       # internship / full-time / contract
    level = Column(String, default="")          # entry / mid / senior
    skills = Column(Text, default="[]")         # JSON list of required skills
    description = Column(Text, default="")
    url = Column(String, default="")            # application URL on the source
    posted_date = Column(String, default="")
    embedding = Column(Text, default="[]")      # JSON list of floats
    # Provenance: where this listing came from and how fresh it is.
    source = Column(String, default="seed")     # seed / remotive / arbeitnow / greenhouse / lever
    source_id = Column(String, default="")      # id within the source, for re-sync
    last_verified_at = Column(String, default="")  # ISO date the source last showed it
    is_expired = Column(Integer, default=0)     # 1 = gone from source or stale
    embedding_model = Column(String, default="")  # which model wrote `embedding`

    def skills_list(self) -> list:
        return json.loads(self.skills or "[]")

    def embedding_list(self) -> list:
        return json.loads(self.embedding or "[]")

    def searchable_text(self) -> str:
        return " ".join([self.title, self.company, self.location,
                         self.job_type, self.level,
                         " ".join(self.skills_list()), self.description])


class ChatMessage(Base):
    """Assistant conversation records (auditable history)."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    role = Column(String)  # user / assistant
    content = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class TailoredDraft(Base):
    __tablename__ = "tailored_drafts"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)
    draft = Column(Text, default="{}")    # JSON tailored resume draft
    changes = Column(Text, default="[]")  # JSON list of source-to-edit changes
    created_at = Column(DateTime, server_default=func.now())


class SyncRun(Base):
    """One automatic or manual refresh of the real job feeds."""
    __tablename__ = "sync_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(String, default="")    # ISO UTC timestamp
    finished_at = Column(String, default="")
    trigger = Column(String, default="")       # startup / schedule / external / manual
    status = Column(String, default="running")  # running / ok / partial / failed
    report = Column(Text, default="{}")        # JSON sync report
