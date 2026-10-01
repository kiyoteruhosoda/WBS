"""Start / Stop を押した時刻（ADR-0018。打刻アプリ task #167）。

アプリは電波の無いところで押された Start / Stop を手元に溜め、繋がってから送る。そのとき
打刻の時刻は**送った時刻ではなく押した時刻**にしたいので、本文に任意の ``at`` を付けられる。

受け取る範囲:

- **未来は断る。** ただし端末の時計のずれとして ``CLOCK_SKEW_ALLOWANCE`` までは「今」に寄せる
  （アプリは ``server_now`` で時計を合わせて送るが、合わせた後のわずかなずれで 422 に
  すると、溜めた打刻が送れなくなる）
- **遠い過去も断る。** ``MAX_PRESS_AGE`` より前の押下は、送り損ねた古い打刻か時計の狂いとみなす
  （それより前は締めの画面で手で足す）
- 送らなければ「今」（Web の画面と同じ）
- 秒未満は落とす（同じ押下の送り直しを、保存した値と突き合わせられるように）
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.exceptions import ValidationError

CLOCK_SKEW_ALLOWANCE = timedelta(seconds=60)
"""これより先の時刻は「未来」として断る。これまでの先は「今」に寄せる。"""

MAX_PRESS_AGE = timedelta(days=7)
"""これより前に押されたことになる打刻は受け取らない。"""


def effective_press_time(pressed_at: datetime | None, now: datetime) -> datetime:
    """打刻に使う時刻（naive な UTC）。``pressed_at`` が無ければ ``now``。"""
    if pressed_at is None:
        return now
    pressed_at = pressed_at.replace(microsecond=0)
    if pressed_at > now + CLOCK_SKEW_ALLOWANCE:
        raise ValidationError("at must not be in the future")
    if pressed_at < now - MAX_PRESS_AGE:
        raise ValidationError(
            f"at is too far in the past (at most {MAX_PRESS_AGE.days} days ago);"
            " add it on the closing screen instead"
        )
    return min(pressed_at, now)


__all__ = ["CLOCK_SKEW_ALLOWANCE", "MAX_PRESS_AGE", "effective_press_time"]
