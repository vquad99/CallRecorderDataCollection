"""Participants, their project links and consent records (PART-*)."""

from __future__ import annotations

import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Literal, get_args

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ColumnElement,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Select,
    String,
    Text,
    UniqueConstraint,
    and_,
    false,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# WITHDRAWN only on answers given before D-129 (nobody can withdraw since).
ConsentStatus = Literal["GIVEN", "REFUSED", "WITHDRAWN"]
# Everything but DIGITAL (the participant's own answer) was noted by a moderator before D-129.
ConsentMethod = Literal["VERBAL_RECORDED", "VERBAL_NOTED", "WRITTEN", "DIGITAL"]
CONSENT_STATUSES: tuple[str, ...] = get_args(ConsentStatus)
CONSENT_METHODS: tuple[str, ...] = get_args(ConsentMethod)

# Speaker details (D-143): the codes and limits, which speakers.py checks with clear words and the
# database keeps as constraints.
MIN_AGE, MAX_AGE = 20, 60
GENDER_CODES = ("MALE", "FEMALE")
EDUCATION_CODES = (
    "PRIMARY",
    "SECONDARY",
    "HIGHER_SECONDARY",
    "DIPLOMA",
    "BACHELORS",
    "MASTERS",
    "PHD",
    "OTHER",
)
EDUCATION_MEDIUM_CODES = ("ENGLISH", "NON_ENGLISH")
PINCODE_COLUMNS = ("current_pincode", "native_pincode", "recording_pincode")


def _one_of(column: str, codes: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(c) for c in codes)})"


SPEAKER_CHECKS = {
    "age_range": f"age IS NULL OR age BETWEEN {MIN_AGE} AND {MAX_AGE}",
    "gender_allowed": _one_of("gender", GENDER_CODES),
    "education_allowed": _one_of("education", EDUCATION_CODES),
    "education_medium_allowed": _one_of("education_medium", EDUCATION_MEDIUM_CODES),
    "pincode_format": " AND ".join(
        f"({c} IS NULL OR {c} ~ '^[1-9][0-9]{{5}}$')" for c in PINCODE_COLUMNS
    ),
}


class Participant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "participants"
    __table_args__ = (
        CheckConstraint("participant_code ~ '^P[0-9]{6,}$'", name="code_format"),
        Index("ix_participants_phone_hash", "phone_hash"),
        *(CheckConstraint(sql, name=name) for name, sql in SPEAKER_CHECKS.items()),
    )
    participant_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    display_label: Mapped[str] = mapped_column(String(200), nullable=False)
    # Phone number encrypted with DATA_ENCRYPTION_KEY; the keyed hash finds duplicates without
    # decrypting; the two-digit hint lets masked views show "......12".
    phone_e164_enc: Mapped[str | None] = mapped_column(Text)
    phone_hash: Mapped[str | None] = mapped_column(String(64))
    phone_hint: Mapped[str | None] = mapped_column(String(2))
    # Optional email address, encrypted; used to send the participant their personal link.
    email_enc: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str] = mapped_column(String(35), nullable=False)
    dialect: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    # The participant's native district (where they were born), free text; the dashboard filters
    # by it (D-121). One of the speaker details below (D-143), kept under its first name.
    district: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    # Speaker details (D-143), checked by speakers.py; empty for people saved before them.
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(10))
    current_state: Mapped[str | None] = mapped_column(String(60))
    current_district: Mapped[str | None] = mapped_column(String(100))
    current_pincode: Mapped[str | None] = mapped_column(String(6))
    native_state: Mapped[str | None] = mapped_column(String(60))
    native_pincode: Mapped[str | None] = mapped_column(String(6))
    native_language: Mapped[str | None] = mapped_column(String(50))
    education: Mapped[str | None] = mapped_column(String(20))
    education_medium: Mapped[str | None] = mapped_column(String(20))
    recording_state: Mapped[str | None] = mapped_column(String(60))
    recording_district: Mapped[str | None] = mapped_column(String(100))
    recording_pincode: Mapped[str | None] = mapped_column(String(6))
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    deletion_reason: Mapped[str | None] = mapped_column(Text)


class ParticipantProjectLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "participant_project_links"
    __table_args__ = (
        UniqueConstraint("participant_id", "project_id", name="uq_participant_project_links_pair"),
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class ConsentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per consent event. What the rows mean is decided in `consent.py` only: the newest
    own answer of a participant in a project is their consent there (D-129)."""

    __tablename__ = "consent_records"
    __table_args__ = (
        CheckConstraint(f"status IN {CONSENT_STATUSES}", name="status_allowed"),
        CheckConstraint(f"method IN {CONSENT_METHODS}", name="method_allowed"),
        Index("ix_consent_records_participant_task", "participant_id", "task_id"),
        # A task's own consent records (task page, delete check), without the participant.
        Index("ix_consent_records_task", "task_id"),
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    # The moderator who noted it for a task (before D-129); empty when the participant answered
    # the consent form themselves on their personal page (method DIGITAL, D-067).
    captured_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    # Set when the participant answered on a link that was shown to this staff member, who could
    # have typed the answer: the consent record says so (D-088).
    link_shown_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # The consent form text the participant answered (their own answers only, D-068), kept so a
    # later change of the project's form cannot change what they agreed to.
    form_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # The staff review of an own "agree" answer that existed from D-073 to D-129, kept as history:
    # APPROVED or REJECTED (with a note) on older answers, empty on answers since. A REJECTED
    # answer does not count as agreed (consent.word); nothing else reads these columns.
    review_status: Mapped[str | None] = mapped_column(String(20))
    review_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @hybrid_property
    def is_own_answer(self) -> bool:
        """The participant's own answer on the project's consent form (D-067): not noted for a
        task, not recorded by staff."""
        return self.task_id is None and self.captured_by is None

    @is_own_answer.inplace.expression
    @classmethod
    def _is_own_answer_expression(cls) -> ColumnElement[bool]:
        return and_(cls.task_id.is_(None), cls.captured_by.is_(None))


# Uploaded documents (D-144): a participant's signed consent form for one project (scanned), and
# their address proof, one for the person whatever the project. The file types documents.py
# accepts, recognised by their first bytes.
CONSENT_FORM, ADDRESS_PROOF = "CONSENT_FORM", "ADDRESS_PROOF"
DOCUMENT_KINDS = (CONSENT_FORM, ADDRESS_PROOF)
DOCUMENT_TYPES = ("application/pdf", "image/jpeg", "image/png")


class ParticipantDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded file (D-144). A new upload replaces the current one of its kind: the older
    row stays, with `replaced_at`, for the record. Only the current one counts."""

    __tablename__ = "participant_documents"
    __table_args__ = (
        CheckConstraint(f"kind IN {DOCUMENT_KINDS}", name="kind_allowed"),
        CheckConstraint(f"content_type IN {DOCUMENT_TYPES}", name="content_type_allowed"),
        # A consent form belongs to a project; an address proof to the person only.
        CheckConstraint(
            f"(kind = '{CONSENT_FORM}') = (project_id IS NOT NULL)", name="project_for_consent_form"
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        # At most one current document of a kind: per project for consent forms.
        Index(
            "uq_participant_documents_current_consent_form",
            "participant_id",
            "project_id",
            unique=True,
            postgresql_where=text(
                f"kind = '{CONSENT_FORM}' AND replaced_at IS NULL AND removed_at IS NULL"
            ),
        ),
        Index(
            "uq_participant_documents_current_address_proof",
            "participant_id",
            unique=True,
            postgresql_where=text(
                f"kind = '{ADDRESS_PROOF}' AND replaced_at IS NULL AND removed_at IS NULL"
            ),
        ),
        Index("ix_participant_documents_participant_kind", "participant_id", "kind"),
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False
    )
    # The project of a consent form; empty for an address proof.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    # The name the file had on the uploader's computer, for people to recognise it.
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Found from the file's first bytes, not taken from the browser.
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set when a newer upload of the same kind took its place.
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    # Set when the file was deleted from storage because the participant was removed (address
    # proofs only: a signed consent form stays as the record of consent, like consent records).
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @hybrid_property
    def is_current(self) -> bool:
        return self.replaced_at is None and self.removed_at is None

    @is_current.inplace.expression
    @classmethod
    def _is_current_expression(cls) -> ColumnElement[bool]:
        return and_(cls.replaced_at.is_(None), cls.removed_at.is_(None))


def of_project(
    project_id: uuid.UUID, kinds: Collection[str] = DOCUMENT_KINDS
) -> ColumnElement[bool]:
    """Documents of these kinds that count in a project: its consent forms, and the person's
    address proof (which belongs to no project)."""
    which = []
    if CONSENT_FORM in kinds:
        which.append(
            and_(
                ParticipantDocument.kind == CONSENT_FORM,
                ParticipantDocument.project_id == project_id,
            )
        )
    if ADDRESS_PROOF in kinds:
        which.append(ParticipantDocument.kind == ADDRESS_PROOF)
    return or_(false(), *which)


def current_documents(
    project_id: uuid.UUID,
    participant_ids: Collection[uuid.UUID],
    kinds: Collection[str] = DOCUMENT_KINDS,
) -> Select[ParticipantDocument]:
    """The participants' current documents of these kinds that count in this project."""
    return select(ParticipantDocument).where(
        ParticipantDocument.participant_id.in_(list(participant_ids)),
        ParticipantDocument.is_current,
        of_project(project_id, kinds),
    )


class ParticipantPortalLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A participant's personal page link for one project (D-067). Only the hash of the secret is
    stored; the link itself is shown once, to the staff member who creates it."""

    __tablename__ = "participant_portal_links"
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # True when the link was shown to the staff member (copy and hand over), false when only
    # emailed to the participant: an answer on a shown link may have been typed by staff (D-088).
    # Links are only emailed now; older rows may still be true.
    shown_to_staff: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
