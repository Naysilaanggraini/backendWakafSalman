"""Operator commands; never exposed as HTTP endpoints."""
import click
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from extensions import db
from models import User


def register_commands(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin(email, name, password):
        """Create a new administrator with an interactive password prompt."""
        email, name = email.strip().lower(), name.strip()
        if not name or len(name) > 150 or "@" not in email or len(email) > 150:
            raise click.ClickException("Nama atau email tidak valid")
        if len(password) < 12:
            raise click.ClickException("Password admin minimal 12 karakter")
        if db.session.execute(db.select(User).where(func.lower(User.email) == email)).scalar_one_or_none():
            raise click.ClickException("Email sudah terdaftar; akun existing tidak diubah")
        db.session.add(User(nama=name, email=email, password=generate_password_hash(password),
                            role="admin", status="aktif"))
        db.session.commit()
        click.echo("Admin berhasil dibuat")
