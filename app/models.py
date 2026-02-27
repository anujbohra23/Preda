from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, nullable=False, unique=True, index=True)
    pw_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)
    deleted_at = db.Column(db.Text, nullable=True)
    preferred_language = db.Column(db.Text, nullable=False, default="en")

    sessions = db.relationship(
        "Session", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    audit_logs = db.relationship(
        "AuditLog", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def set_password(self, password: str):
        self.pw_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.pw_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    title = db.Column(db.Text, nullable=True)
    status = db.Column(db.Text, nullable=False, default="intake")
    safety_flagged = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)
    updated_at = db.Column(db.Text, nullable=False, default=utcnow)

    intake_fields = db.relationship(
        "IntakeField", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )
    uploads = db.relationship(
        "Upload", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )
    disease_results = db.relationship(
        "DiseaseResult", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )
    chat_messages = db.relationship(
        "ChatMessage", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )
    reports = db.relationship(
        "Report", backref="session", lazy="dynamic", cascade="all, delete-orphan"
    )


class IntakeField(db.Model):
    __tablename__ = "intake_fields"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    field_name = db.Column(db.Text, nullable=False)
    field_value = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)

    __table_args__ = (db.UniqueConstraint("session_id", "field_name"),)


class Upload(db.Model):
    __tablename__ = "uploads"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_name = db.Column(db.Text, nullable=False)
    stored_path = db.Column(db.Text, nullable=False)
    file_size_bytes = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.Text, nullable=True)
    upload_status = db.Column(db.Text, nullable=False, default="pending")
    created_at = db.Column(db.Text, nullable=False, default=utcnow)

    chunks = db.relationship(
        "ExtractedChunk", backref="upload", lazy="dynamic", cascade="all, delete-orphan"
    )


class ExtractedChunk(db.Model):
    __tablename__ = "extracted_chunks"

    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(
        db.Integer, db.ForeignKey("uploads.id"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    chunk_text = db.Column(db.Text, nullable=False)
    edited_text = db.Column(db.Text, nullable=True)
    is_confirmed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)

    rag_retrievals = db.relationship(
        "RagRetrieval", backref="chunk", lazy="dynamic", cascade="all, delete-orphan"
    )


class DiseaseCatalog(db.Model):
    __tablename__ = "disease_catalog"

    id = db.Column(db.Integer, primary_key=True)
    disease_name = db.Column(db.Text, nullable=False, unique=True, index=True)
    icd_code = db.Column(db.Text, nullable=True)
    short_desc = db.Column(db.Text, nullable=True)
    embedding_blob = db.Column(db.LargeBinary, nullable=True)
    # updated_at = db.Column(db.Text, nullable=False, default=utcnow)

    results = db.relationship("DiseaseResult", backref="disease", lazy="dynamic")


class DiseaseResult(db.Model):
    __tablename__ = "disease_results"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    disease_id = db.Column(
        db.Integer, db.ForeignKey("disease_catalog.id"), nullable=False
    )
    rank = db.Column(db.Integer, nullable=False)
    similarity_score = db.Column(db.Float, nullable=False)
    explanation_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)

    __table_args__ = (db.UniqueConstraint("session_id", "rank"),)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    role = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text, nullable=False)
    use_private_only = db.Column(db.Integer, default=0)
    safety_triggered = db.Column(db.Integer, default=0)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)

    rag_retrievals = db.relationship(
        "RagRetrieval",
        backref="chat_message",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class RagRetrieval(db.Model):
    __tablename__ = "rag_retrievals"

    id = db.Column(db.Integer, primary_key=True)
    chat_message_id = db.Column(
        db.Integer, db.ForeignKey("chat_messages.id"), nullable=False, index=True
    )
    chunk_id = db.Column(
        db.Integer, db.ForeignKey("extracted_chunks.id"), nullable=False
    )
    similarity_score = db.Column(db.Float, nullable=False)
    citation_label = db.Column(db.Text, nullable=True)
    source_doc_name = db.Column(db.Text, nullable=True)


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    report_type = db.Column(db.Text, nullable=False)
    content_json = db.Column(db.Text, nullable=False)
    pdf_path = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.Text, nullable=False, default=utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    session_id = db.Column(db.Integer, nullable=True)
    event_type = db.Column(db.Text, nullable=False, index=True)
    event_detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    title = db.Column(db.Text, nullable=True)
    doctor_name = db.Column(db.Text, nullable=True)
    appointment_date = db.Column(db.Text, nullable=True)
    capture_method = db.Column(db.Text, nullable=True)
    audio_path = db.Column(db.Text, nullable=True)
    raw_transcript = db.Column(db.Text, nullable=True)
    summary_json = db.Column(db.Text, nullable=True)
    followup_date = db.Column(db.Text, nullable=True)
    status = db.Column(db.Text, nullable=False, default="pending")
    created_at = db.Column(db.Text, nullable=False, default=utcnow)

    actions = db.relationship(
        "AppointmentAction",
        backref="appointment",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class AppointmentAction(db.Model):
    __tablename__ = "appointment_actions"

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(
        db.Integer, db.ForeignKey("appointments.id"), nullable=False
    )
    action_type = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    detail = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Text, nullable=True)
    is_completed = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.Text, nullable=False, default=utcnow)