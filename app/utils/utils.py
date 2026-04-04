from dataclasses import dataclass


@dataclass
class RfidClientTapPayload:
    pico_id: str
    tag_id: str


def parse_tap_response(payload: str) -> RfidClientTapPayload | None:
    fields = [f.strip() for f in payload.split("|")]
    if len(fields) != 2:
        print(f"[parse] Expected 2 fields, got {len(fields)}")
        return None
    return RfidClientTapPayload(
        pico_id=fields[0],
        tag_id=fields[1],
    )


@dataclass
class RfidServerTapPayload:
    pico_id: str
    tag_id: str
    user_pref_name: str
    points: int
    streak_score: int
    special_message: str

    def __str__(self) -> str:
        return f"{self.pico_id}|{self.tag_id}|{self.user_pref_name}|{self.points}|{self.streak_score}|{self.special_message}"
