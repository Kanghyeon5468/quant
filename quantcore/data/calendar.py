"""US cash-session clocks, including DST, holidays and early closes."""
import pandas as pd


def sessions(start, end, as_of=None):
    import exchange_calendars as xc
    first, last = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if first > last:
        raise ValueError('start must not follow end')
    calendar = xc.get_calendar('XNYS', start=str((first-pd.Timedelta(days=14)).date()),
                               end=str((last+pd.Timedelta(days=14)).date()))
    schedule = calendar.schedule.loc[first:last, ['open', 'close']].copy()
    schedule.index = schedule.index.strftime('%Y-%m-%d')
    schedule.index.name = 'session'
    if as_of is not None:
        stamp = pd.Timestamp(as_of)
        if stamp.tzinfo is None:
            raise ValueError('as_of requires timezone')
        schedule = schedule[schedule['close']+pd.Timedelta(minutes=1) <= stamp]
    return schedule


def action_open(day, strict_after=False):
    day = pd.Timestamp(day).date()
    window = sessions(day, day+pd.Timedelta(days=14))
    if strict_after:
        window = window[window.index > str(day)]
    if window.empty:
        raise ValueError('no session for corporate action')
    return pd.Timestamp(window.iloc[0]['open'])
