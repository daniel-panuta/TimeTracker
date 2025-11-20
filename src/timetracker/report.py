import datetime as dt
from .db import connect, daily_totals

def fmt(sec):
    sec = int(round(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def run(days=30):
    """Afișează raportul cu timpul activ din ultimele X zile."""
    since = (dt.date.today() - dt.timedelta(days=days-1)).isoformat()
    con = connect()
    rows = daily_totals(con, since)
    con.close()

    if not rows:
        print("Niciun interval găsit.")
        return

    print("Ziua          Timp activ")
    print("------------------------")
    for day, sec in rows:
        print(f"{day}    {fmt(sec or 0)}")
