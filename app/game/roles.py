from enum import Enum
import secrets


class Role(str, Enum):
    CITIZEN = "citizen"
    DETECTIVE = "detective"
    DOCTOR = "doctor"
    SHERIFF = "sheriff"
    MAFIA = "mafia"
    DON = "don"


ROLE_TEAM: dict[Role, str] = {
    Role.CITIZEN: "town",
    Role.DETECTIVE: "town",
    Role.DOCTOR: "town",
    Role.SHERIFF: "town",
    Role.MAFIA: "mafia",
    Role.DON: "mafia",
}

ROLE_TITLE: dict[Role, str] = {
    Role.CITIZEN: "👨‍🌾 Tinch aholi",
    Role.DETECTIVE: "🕵️ Detektiv",
    Role.DOCTOR: "👨‍⚕️ Doktor",
    Role.SHERIFF: "🔫 Sherif",
    Role.MAFIA: "🔪 Mafiya",
    Role.DON: "🤵 Don",
}

ROLE_INSTRUCTIONS: dict[Role, str] = {
    Role.CITIZEN: "Kunduzgi muhokama va ovoz berishda mafiyani topishga yordam bering.",
    Role.DETECTIVE: "Har kecha bitta tirik o‘yinchini tekshiring. Natija sizga maxfiy yuboriladi.",
    Role.DOCTOR: "Har kecha bitta tirik o‘yinchini himoya qiling.",
    Role.SHERIFF: "Har kecha gumon qilingan o‘yinchini tekshiring.",
    Role.MAFIA: "Kechasi boshqa mafiya a’zolari bilan nishon tanlang.",
    Role.DON: "Mafiya jamoasidasiz. Detektiv tekshiruvida maxsus himoyangiz bor.",
}


class RoleAssignmentError(ValueError):
    """Raised when a role assignment request is invalid."""


def assign_roles(player_ids: list[int]) -> dict[int, Role]:
    """Assign a balanced role set using a cryptographically secure shuffle."""
    if len(player_ids) < 4:
        raise RoleAssignmentError("O‘yinni boshlash uchun kamida 4 o‘yinchi kerak.")
    if len(set(player_ids)) != len(player_ids):
        raise RoleAssignmentError("O‘yinchilar ro‘yxatida takroriy ID bor.")

    count = len(player_ids)
    mafia_count = max(1, count // 4)
    roles: list[Role] = []

    if mafia_count >= 2:
        roles.append(Role.DON)
        roles.extend([Role.MAFIA] * (mafia_count - 1))
    else:
        roles.append(Role.MAFIA)

    roles.append(Role.DETECTIVE)
    if count >= 5:
        roles.append(Role.DOCTOR)
    if count >= 9:
        roles.append(Role.SHERIFF)

    roles.extend([Role.CITIZEN] * (count - len(roles)))
    if len(roles) != count:
        raise RoleAssignmentError("Ushbu o‘yinchi soni uchun rollar muvozanatini tuzib bo‘lmadi.")

    secrets.SystemRandom().shuffle(roles)
    return dict(zip(player_ids, roles, strict=True))


def is_mafia_role(role: Role) -> bool:
    return ROLE_TEAM[role] == "mafia"


def investigation_result(target_role: Role) -> str:
    """Return the result visible to a Detective or Sheriff."""
    if target_role == Role.DON:
        return "not_mafia"
    return "mafia" if is_mafia_role(target_role) else "not_mafia"
