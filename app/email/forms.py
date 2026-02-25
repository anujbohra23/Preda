from flask_wtf import FlaskForm
from wtforms import BooleanField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class EmailConsentForm(FlaskForm):
    consent_note = TextAreaField(
        "Reason for sharing",
        validators=[DataRequired(message="Please add a brief note."), Length(max=500)],
    )
    explicit_consent = BooleanField(
        "I explicitly consent to sharing this informational summary "
        "with my saved pharmacy, and understand it is not a prescription "
        "or diagnosis.",
        validators=[DataRequired(message="You must check this box to proceed.")],
    )
    submit = SubmitField("Send to My Pharmacy")
