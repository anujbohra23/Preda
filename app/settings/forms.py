from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import Email, Length, Optional


class PharmacySettingsForm(FlaskForm):
    pharmacy_name = StringField(
        "Pharmacy Name", validators=[Optional(), Length(max=120)]
    )
    pharmacy_email = StringField(
        "Pharmacy Email Address", validators=[Optional(), Email(), Length(max=254)]
    )
    pharmacy_address = TextAreaField(
        "Pharmacy Address (optional)", validators=[Optional(), Length(max=300)]
    )
    submit = SubmitField("Save Pharmacy Details")
