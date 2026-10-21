"""Разбор текстов мониторинговых каналов: тип угрозы, уровень, место, направление."""
import json, math, re, time, pathlib

CITIES = json.loads(pathlib.Path(__file__).with_name("cities.json").read_text("utf-8"))

UAV = r"бпла|беспилот|безпілот|дрон|шахед|шахід|shahed|герань|гера[нн]ь|ударн\w+ бпла"
MISSILE = r"ракет|баллист|балістик|крылат|крилат|калибр|калібр|искандер|іскандер|кинжал|кінджал|х-?101|х-?22|циркон|циркон|каб\b|кабы|кабів"
AVIA = r"авиац|авіац|ту-?95|ту-?160|ту-?22|миг-?31|міг-?31|су-?34|су-?35|стратег"
RED_CTX = r"над |заходит|заходять|заходить|летит на|летить на|курс на|курсом на|прилёт|приліт|взрыв|вибух|в районе|у районі|уже в|вже у|угроза удар|загроза удар"
CLEAR = r"отбой|відбій|угроза миновала|загроза минула|чисто\b"

TYPE_RULES = [("missile", MISSILE), ("uav", UAV), ("aviation", AVIA)]

COMPASS = [  # (regex стороны, азимут стороны света)
    (r"северо-восточ\w+|північно-східн\w+|північний схід|півн\w*-схід\w*", 45),
    (r"юго-восточ\w+|південно-східн\w+|південний схід", 135),
    (r"юго-западн\w+|південно-західн\w+|південний захід", 225),
    (r"северо-западн\w+|північно-західн\w+|північний захід", 315),
    (r"север\w*|півн\w*|північ\w*", 0),
    (r"восток\w*|восточн\w+|схід\w*|східн\w+", 90),
    (r"юг\w*|півд\w*|південь\w*|південн\w+", 180),
    (r"запад\w*|західн\w+|захід\w*", 270),
]

def bearing(a, b):
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def find_places(low):
    found = {}
    for c in CITIES:
        for s in c["stems"]:
            m = re.search(r"(?<!\w)" + re.escape(s) + r"\w*", low)
            if m and (c["name"] not in found or m.start() < found[c["name"]][0]):
                found[c["name"]] = (m.start(), c)
    return sorted(found.values(), key=lambda x: x[0])

def role(low, i):
    ctx = low[max(0, i - 16):i]
    if re.search(r"(курс\w* на|напрям\w* на|напрямку|в бік|у бік|в сторону|на)\s*$", ctx):
        return "target"
    if re.search(r"(из|з|від|со стороны|зі сторони|от)\s*$", ctx):
        return "origin"
    return "place"

def compass_heading(low):
    # "с севера"/"з півночі" -> летит в противоположную сторону; "на север"/"у північному напрямку" -> прямо
    for rx, az in COMPASS:
        if re.search(r"(?:с|со|из|з|від|зі)\s+(?:" + rx + r")", low):
            return (az + 180) % 360
    for rx, az in COMPASS:
        if re.search(r"(?:на|в|у|к|до)\s+(?:" + rx + r")|(?:" + rx + r")\w*\s+(?:направлен|напрямк|курс)", low):
            return az
    return None

def is_clear(text):
    return bool(re.search(CLEAR, text.lower()))

def clear_places(text):
    return [c["name"] for _, c in find_places(text.lower())]

def parse_message(text, source="", ts=None):
    low = text.lower()
    typ = next((t for t, rx in TYPE_RULES if re.search(rx, low)), None)
    if not typ:
        return None
    places = find_places(low)
    origin = target = place = None
    for i, c in places:
        r = role(low, i)
        if r == "target" and not target: target = c
        elif r == "origin" and not origin: origin = c
        elif not place: place = c
    anchor = place or origin or target
    if not anchor:
        return None
    heading = None
    tgt = None
    if target and target is not anchor:
        tgt = {"name": target["name"], "lat": target["lat"], "lon": target["lon"]}
        heading = bearing((anchor["lat"], anchor["lon"]), (target["lat"], target["lon"]))
    elif target and origin:
        tgt = {"name": target["name"], "lat": target["lat"], "lon": target["lon"]}
        heading = bearing((origin["lat"], origin["lon"]), (target["lat"], target["lon"]))
    if heading is None:
        heading = compass_heading(low)
    level = "red" if (typ == "missile" or re.search(RED_CTX, low)) else "yellow"
    return {
        "id": f"{source}:{int(ts or time.time()*1000)}",
        "ts": ts or time.time(), "type": typ, "level": level,
        "place": anchor["name"], "lat": anchor["lat"], "lon": anchor["lon"],
        "heading": None if heading is None else round(heading),
        "target": tgt, "source": source, "text": text[:280],
    }
