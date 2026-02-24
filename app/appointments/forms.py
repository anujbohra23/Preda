from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, BooleanField
from wtforms.validators import Optional, Length, DataRequired


class AppointmentMetaForm(FlaskForm):
    doctor_name      = StringField(
        'Doctor / Clinician Name',
        validators=[Optional(), Length(max=120)]
    )
    appointment_date = StringField(
        'Appointment Date',
        validators=[Optional(), Length(max=30)]
    )
    title = StringField(
        'Title (optional)',
        validators=[Optional(), Length(max=200)]
    )


class AudioUploadForm(FlaskForm):
    doctor_name      = StringField('Doctor Name', validators=[Optional(), Length(max=120)])
    appointment_date = StringField('Date', validators=[Optional()])
    audio_file       = FileField(
        'Audio File',
        validators=[
            FileAllowed(
                ['mp3', 'wav', 'm4a', 'webm', 'ogg'],
                'Audio files only (mp3, wav, m4a, webm, ogg)'
            )
        ]
    )
    submit = SubmitField('Upload and Transcribe')


class ManualNotesForm(FlaskForm):
    doctor_name      = StringField('Doctor Name', validators=[Optional(), Length(max=120)])
    appointment_date = StringField('Date', validators=[Optional()])
    notes            = TextAreaField(
        'Appointment Notes',
        validators=[
            DataRequired(message='Please enter your appointment notes.'),
            Length(min=20, max=10000)
        ]
    )
    submit = SubmitField('Generate Summary')


class ConsentForm(FlaskForm):
    confirmed = BooleanField(
        'I confirm my doctor has consented to being recorded.',
        validators=[DataRequired(message='You must confirm consent before recording.')]
    )
    submit = SubmitField('Confirmed — Continue')