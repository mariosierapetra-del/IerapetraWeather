"""Υπολογίζει τη σταθμισμένη πρόγνωση για την Ιεράπετρα και τη γράφει στο forecast.json.
Χρησιμοποιεί μόνο την τυπική βιβλιοθήκη της Python."""
import json, math, urllib.request
from datetime import date, datetime, timedelta, timezone

LAT, LON = 35.01, 25.74
GUST_WARN = 50
MODELS = {"ecmwf_ifs025": "ECMWF", "gfs_seamless": "GFS", "icon_seamless": "ICON", "icon_eu": "ICON-EU",
          "meteofrance_seamless": "Météo-France", "ukmo_seamless": "UK Met"}
KEYS = list(MODELS)
WEEK = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
DIRNAMES = ["Βόρειος", "Βορειοανατολικός", "Ανατολικός", "Νοτιοανατολικός", "Νότιος", "Νοτιοδυτικός", "Δυτικός", "Βορειοδυτικός"]
COMPASS = ["Β", "ΒΑ", "Α", "ΝΑ", "Ν", "ΝΔ", "Δ", "ΒΔ"]

def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

def avg(xs):
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None

def wavg(vals, ws):
    s = t = 0
    for v, w in zip(vals, ws):
        if v is not None:
            s += v * w; t += w
    return s / t if t else None

def dir_mean(degs, ws):
    x = y = 0
    for d, w in zip(degs, ws):
        if d is not None:
            x += w * math.sin(math.radians(d)); y += w * math.cos(math.radians(d))
    if not x and not y:
        return None
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def bft(kmh):
    return sum(1 for t in [1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118] if kmh >= t)

def at(d, field, m, i):
    arr = d.get(f"{field}_{m}") or []
    return arr[i] if i < len(arr) else None

def get_weights():
    ones = {m: 1.0 for m in KEYS}
    try:
        today = date.today()
        rng = f"&start_date={today - timedelta(days=20)}&end_date={today - timedelta(days=6)}"
        base = f"?latitude={LAT}&longitude={LON}{rng}&daily=temperature_2m_max,wind_speed_10m_max&timezone=Europe%2FAthens"
        ref = get("https://archive-api.open-meteo.com/v1/archive" + base)["daily"]
        hist = get("https://historical-forecast-api.open-meteo.com/v1/forecast" + base + "&models=" + ",".join(KEYS))["daily"]
        raw = {}
        for m in KEYS:
            eT, eW = [], []
            for i in range(len(ref["time"])):
                t, w = at(hist, "temperature_2m_max", m, i), at(hist, "wind_speed_10m_max", m, i)
                rt, rw = ref["temperature_2m_max"][i], ref["wind_speed_10m_max"][i]
                if t is not None and rt is not None: eT.append(abs(t - rt))
                if w is not None and rw is not None: eW.append(abs(w - rw))
            if len(eT) >= 5 and len(eW) >= 5:
                raw[m] = 1 / (avg(eT) + avg(eW) / 5 + 0.5)
        if len(raw) < 2:
            return ones, False
        mean = avg(list(raw.values()))
        w = dict(ones)
        for k, v in raw.items():
            w[k] = v / mean
        return w, True
    except Exception as e:
        print("weights failed:", e)
        return ones, False

def icon(rain, gust):
    if rain >= 5: return "🌧️"
    if rain >= 1: return "🌦️"
    return "💨" if gust >= GUST_WARN else "☀️"

def day_text(o):
    p = ["Βροχερή μέρα." if o["rain"] >= 5 else "Πιθανές τοπικές βροχές." if o["rain"] >= 1 else "Χωρίς βροχή."]
    p.append(f"Θερμοκρασία από {o['tmin']}° έως {o['tmax']}°.")
    who = "Άνεμος" if o["dir"] is None else f"{DIRNAMES[round(o['dir'] / 45) % 8]} άνεμος"
    p.append(f"{who} {o['bft']} Μπφ (γύρω στα {o['wind']} km/h), με ριπές έως {o['gust']} km/h.")
    if o["gust"] >= GUST_WARN: p.append("Προσοχή στις ριπές.")
    return " ".join(p)

def main():
    weights, ok = get_weights()
    W = [weights[m] for m in KEYS]
    url = ("https://api.open-meteo.com/v1/forecast" f"?latitude={LAT}&longitude={LON}"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant"
           f"&models={','.join(KEYS)}&timezone=Europe%2FAthens&forecast_days=5")
    d = get(url)["daily"]
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "weights_ok": ok, "days": []}
    for i, day in enumerate(d["time"]):
        col = lambda f: [at(d, f, m, i) for m in KEYS]
        dirv = dir_mean(col("wind_direction_10m_dominant"), W)
        o = {"date": day, "name": WEEK[date.fromisoformat(day).weekday()],
             "tmax": round(wavg(col("temperature_2m_max"), W)), "tmin": round(wavg(col("temperature_2m_min"), W)),
             "rain": round(wavg(col("precipitation_sum"), W), 1), "wind": round(wavg(col("wind_speed_10m_max"), W)),
             "gust": round(wavg(col("wind_gusts_10m_max"), W)), "dir": None if dirv is None else round(dirv)}
        o["dir_text"] = "" if o["dir"] is None else COMPASS[round(o["dir"] / 45) % 8]
        o["bft"] = bft(o["wind"])
        o["gust_bft"] = bft(o["gust"])
        o["short"] = o["name"][:3]
        o["icon"] = icon(o["rain"], o["gust"])
        o["text"] = day_text(o)
        out["days"].append(o)
        for k, v in o.items():            # επίπεδα κλειδιά (d0_tmax κ.λπ.) για εύκολη ανάγνωση από το widget
            out[f"d{i}_{k}"] = v
    with open("forecast.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("ok, weights:", ok)

if __name__ == "__main__":
    main()
              
