import re
from urllib.parse import urlsplit


PROFILE_FIELDS = {"nama", "email", "divisi", "jabatan", "foto_profil"}


def validate_user_data(data, *, create=False, admin=False, allow_phone=False):
    allowed = PROFILE_FIELDS | ({"role", "status"} if admin else set())
    if allow_phone:
        allowed |= {"no_hp"}
    if create:
        allowed |= {"password"}
    if not isinstance(data, dict) or not data:
        return None, "Data user wajib diisi"
    if set(data) - allowed:
        return None, "Ada field yang tidak dapat diubah"

    values = {}
    limits = {"nama": 150, "email": 150, "divisi": 100, "jabatan": 100, "foto_profil": 500, "no_hp": 30}
    for key, value in data.items():
        if key in {"divisi", "jabatan", "foto_profil"} and value is None:
            value = ""
        if not isinstance(value, str):
            return None, f"{key} harus berupa teks"
        values[key] = value if key == "password" else value.strip()
        if key in limits and len(values[key]) > limits[key]:
            return None, f"{key} maksimal {limits[key]} karakter"

    for key in ("nama", "email", "password") if create else ("nama", "email"):
        if (create or key in values) and not values.get(key):
            return None, f"{key} wajib diisi"
    if "email" in values and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"]):
        return None, "Masukkan alamat email yang valid"
    if values.get("no_hp") and (not re.fullmatch(r"\+?[0-9 ()-]+", values["no_hp"]) or not re.search(r"[0-9]", values["no_hp"])):
        return None, "No. HP hanya boleh berisi angka, awalan +, spasi, tanda kurung, atau tanda hubung"
    if "role" in values and values["role"] not in {"admin", "user"}:
        return None, "Role tidak valid"
    if "status" in values and values["status"] not in {"aktif", "nonaktif"}:
        return None, "Status tidak valid"
    if values.get("foto_profil"):
        try:
            url = urlsplit(values["foto_profil"])
            valid = url.scheme in {"http", "https"} and bool(url.hostname)
        except ValueError:
            valid = False
        if not valid:
            return None, "Foto profil harus berupa URL http atau https"
    return values, None
