from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import Length, Optional


class NewSessionForm(FlaskForm):
    title = StringField(
        "Session Title (optional)", validators=[Optional(), Length(max=120)]
    )
    submit = SubmitField("Create Session")
