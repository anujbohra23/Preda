import json
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from ..extensions import db
from ..models import User, AuditLog
from .forms import SignupForm, LoginForm
from ..extensions import limiter

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _log(user_id: int, event: str, detail: dict = None):
    log = AuditLog(
        user_id=user_id,
        event_type=event,
        event_detail=json.dumps(detail or {})
    )
    db.session.add(log)
    db.session.commit()


@auth_bp.route('/signup', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('sessions.dashboard'))

    form = SignupForm()

    if form.validate_on_submit():
        user = User(email=form.email.data.lower().strip())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        _log(user.id, 'signup')
        login_user(user)
        flash('Account created successfully. Welcome!', 'success')
        return redirect(url_for('sessions.dashboard'))

    return render_template('auth/signup.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('sessions.dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(
            email=form.email.data.lower().strip()
        ).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html', form=form)

        login_user(user)
        _log(user.id, 'login')

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(url_for('sessions.dashboard'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    _log(current_user.id, 'logout')
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.landing'))