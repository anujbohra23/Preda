from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class IntakeForm(FlaskForm):
    # ── Core symptom fields ────────────────────────────────────────────────
    age = IntegerField(
        "Age",
        validators=[
            DataRequired(message="Age is required."),
            NumberRange(min=0, max=130, message="Enter a valid age."),
        ],
    )
    sex = SelectField(
        "Biological Sex",
        choices=[
            ("", "-- Select --"),
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other"),
            ("prefer_not_to_say", "Prefer not to say"),
        ],
        validators=[DataRequired(message="Please select an option.")],
    )
    chief_complaint = TextAreaField(
        "Chief Complaint",
        validators=[
            DataRequired(message="Please describe your main symptom or concern."),
            Length(max=1000),
        ],
    )
    duration = StringField(
        "How long have you had this symptom?",
        validators=[
            DataRequired(message="Please describe the duration."),
            Length(max=200),
        ],
    )
    medications = TextAreaField(
        "Current Medications (name + dose if known)",
        validators=[Optional(), Length(max=1000)],
    )
    allergies = TextAreaField(
        "Known Allergies", validators=[Optional(), Length(max=500)]
    )
    additional_notes = TextAreaField(
        "Additional Notes", validators=[Optional(), Length(max=2000)]
    )

    # ── Optional PDF upload ────────────────────────────────────────────────
    pdf_file = FileField(
        "Upload a Medical Document (PDF, optional)",
        validators=[
            Optional(),
            FileAllowed(["pdf"], "PDF files only."),
        ],
    )

    submit = SubmitField("Save & Continue")
