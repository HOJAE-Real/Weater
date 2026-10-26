# -*- coding: utf-8 -*-
"""
청주시 흥덕구 복대동 예보 받기 (GitHub Actions가 3시간마다 실행)
- 3시간 간격 예보: 기상청 단기예보 (격자 68, 107)
- 일별 예보: 단기예보(오늘~3일) + 중기예보(그 이후~10일)
- 결과는 forecast.json에 저장. 인증키는 GitHub Secrets의 SERVICE_KEY 사용
"""
import os
import json
import datetime
import urllib.request
import urllib.parse

NX, NY = 68, 107            # 복대동 예보 격자
MID_LAND = "11C10000"       # 중기 육상예보: 충청북도
MID_TA = "11C10301"         # 중기 기온예보: 청주
OUT = "forecast.json"
BASE = "http://apis.data.go.kr/1360000"
KST = datetime.timezone(datetime.timedelta(hours=9))

KEY = os.environ["SERVICE_KEY"].strip()
KEY = KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")

SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY = {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기", "5": "빗방울", "6": "빗방울눈날림", "7": "눈날림"}


def call(path, params):
    q = urllib.parse.urlencode({"pageNo": 1, "dataType": "JSON", **params})
    req = urllib.request.Request(f"{BASE}/{path}?serviceKey={KEY}&{q}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as res:
        data = json.loads(res.read().decode("utf-8"))
    h = data["response"]["header"]
    if h["resultCode"] != "00":
        raise RuntimeError(f"{path}: {h.get('resultMsg')}")
    items = data["response"]["body"]["items"]["item"]
    return items if isinstance(items, list) else [items]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def short_base(now):
    """가장 최근 단기예보 발표시각 (02,05,...,23시, 발표 후 15분 여유)"""
    t = now - datetime.timedelta(minutes=15)
    for h in (23, 20, 17, 14, 11, 8, 5, 2):
        if t.hour >= h:
            return t.strftime("%Y%m%d"), f"{h:02d}00"
    y = t - datetime.timedelta(days=1)
    return y.strftime("%Y%m%d"), "2300"


def get_short(now):
    d, t = short_base(now)
    items = call("VilageFcstInfoService_2.0/getVilageFcst",
                 {"numOfRows": 1500, "base_date": d, "base_time": t, "nx": NX, "ny": NY})
    slots = {}
    for it in items:
        key = it["fcstDate"] + it["fcstTime"]
        slots.setdefault(key, {})[it["category"]] = it["fcstValue"]
    return f"{d} {t[:2]}시", slots


def weather_text(s):
    p = s.get("PTY", "0")
    return PTY.get(p) if p != "0" and p in PTY else SKY.get(s.get("SKY", ""), "–")


def build_hourly(slots):
    out = []
    for key in sorted(slots):
        hh = int(key[8:10])
        if hh % 3:
            continue
        s = slots[key]
        pcp = s.get("PCP", "강수없음")
        out.append({
            "date": f"{key[:4]}-{key[4:6]}-{key[6:8]}", "time": f"{hh:02d}:00",
            "tmp": num(s.get("TMP")), "wx": weather_text(s),
            "pop": num(s.get("POP")), "pcp": "" if pcp == "강수없음" else pcp,
            "reh": num(s.get("REH")), "wsd": num(s.get("WSD")),
        })
    return out


def daily_from_short(slots):
    days = {}
    for key, s in slots.items():
        date = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        hh = int(key[8:10])
        d = days.setdefault(date, {"temps": [], "am": None, "pm": None, "popAm": 0, "popPm": 0})
        t = num(s.get("TMP"))
        if t is not None:
            d["temps"].append(t)
        if "TMN" in s:
            d["min"] = num(s["TMN"])
        if "TMX" in s:
            d["max"] = num(s["TMX"])
        pop = num(s.get("POP")) or 0
        if 6 <= hh < 12:
            d["popAm"] = max(d["popAm"], pop)
            if hh == 9:
                d["am"] = weather_text(s)
        elif 12 <= hh < 18:
            d["popPm"] = max(d["popPm"], pop)
            if hh == 15:
                d["pm"] = weather_text(s)
    out = {}
    for date, d in days.items():
        if not d["temps"]:
            continue
        out[date] = {
            "date": date,
            "min": d.get("min", min(d["temps"])), "max": d.get("max", max(d["temps"])),
            "am": d["am"], "pm": d["pm"], "popAm": d["popAm"], "popPm": d["popPm"],
            "src": "단기",
        }
    return out


def mid_base(now):
    """중기예보 발표시각 (06시, 18시)"""
    t = now - datetime.timedelta(minutes=30)
    if t.hour >= 18:
        return t.strftime("%Y%m%d") + "1800", t.date()
    if t.hour >= 6:
        return t.strftime("%Y%m%d") + "0600", t.date()
    y = t - datetime.timedelta(days=1)
    return y.strftime("%Y%m%d") + "1800", y.date()


def get_mid(now):
    tm, base_date = mid_base(now)
    land = call("MidFcstInfoService/getMidLandFcst", {"numOfRows": 10, "regId": MID_LAND, "tmFc": tm})[0]
    ta = call("MidFcstInfoService/getMidTa", {"numOfRows": 10, "regId": MID_TA, "tmFc": tm})[0]
    out = {}
    for n in range(3, 11):
        date = (base_date + datetime.timedelta(days=n)).isoformat()
        tmin, tmax = num(ta.get(f"taMin{n}")), num(ta.get(f"taMax{n}"))
        if tmin is None and tmax is None:
            continue
        if n <= 7:
            am, pm = land.get(f"wf{n}Am"), land.get(f"wf{n}Pm")
            pa, pp = num(land.get(f"rnSt{n}Am")), num(land.get(f"rnSt{n}Pm"))
        else:
            am = pm = land.get(f"wf{n}")
            pa = pp = num(land.get(f"rnSt{n}"))
        out[date] = {"date": date, "min": tmin, "max": tmax, "am": am, "pm": pm,
                     "popAm": pa, "popPm": pp, "src": "중기"}
    return tm, out


def main():
    now = datetime.datetime.now(KST)
    result = {"place": "청주시 흥덕구 복대동", "updated": now.strftime("%Y-%m-%d %H:%M"),
              "hourly": [], "daily": []}
    ok = False
    daily = {}
    try:
        base, slots = get_short(now)
        result["shortBase"] = base
        result["hourly"] = build_hourly(slots)
        daily.update(daily_from_short(slots))
        ok = True
        print(f"단기예보 {base} 완료: {len(result['hourly'])}개")
    except Exception as e:
        print("단기예보 실패:", e)
    try:
        tm, mid = get_mid(now)
        result["midBase"] = tm
        for date, v in mid.items():
            daily.setdefault(date, v)     # 단기예보가 있는 날은 단기 우선
        ok = True
        print(f"중기예보 {tm} 완료: {len(mid)}일")
    except Exception as e:
        print("중기예보 실패:", e)
    if not ok:
        raise SystemExit("예보를 하나도 받지 못했어요.")
    today = now.date().isoformat()
    result["daily"] = [daily[d] for d in sorted(daily) if d >= today]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
