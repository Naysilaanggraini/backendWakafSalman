from models import UserProfile


def apply_phone(user, values):
    """Consume validated optional phone field; leave omitted values untouched."""
    if "no_hp" not in values:
        return
    phone = values.pop("no_hp") or None
    if user.user_profile is not None:
        user.user_profile.no_hp = phone
    elif phone is not None:
        user.user_profile = UserProfile(no_hp=phone)
