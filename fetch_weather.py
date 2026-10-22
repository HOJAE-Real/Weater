# -*- coding: utf-8 -*-
import os
import json
import datetime
import urllib.request
import urllib.parse

STN_CODE = "131"
START = datetime.date(2020, 1, 1)
DATA_FILE = "data.json"
API_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"

KEY = os.environ["SERVICE_KEY"].strip()
KEY = KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_range(start, end):
    q = urllib.parse.urlencode({
        "pageNo": 1, "numOfRows": 999, "dataType": "JSON",
        "dataCd": "ASOS", "dateCd": "DAY",
        "startDt": start.strftime("%Y%m%d"), "endDt": end.strftime("%Y%m%d"),
        "stnIds": STN_CODE,
    })
    req = urllib.request.Request(f"{API_URL}?serviceKey={KEY}&{q}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as res:
        data = json.loads(res.read().decode("utf-8"))
    header = data["response"]["header"]
    if header["resultCode"] == "03":
        return []
    if header["resultCode"] != "00":
        raise RuntimeError(header.get("resultMsg"))
    items = data["response"]["body"]["items"]["item"]
    return items if isinstance(items, list) else [items]


def main():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {"station": "청주(유)", "days": {}}

    days = store["days"]
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    start = START
    if days:
        start = datetime.date.fromisoformat(max(days)) + datetime.timedelta(days=1)

    cur = start
    while cur <= yesterday:
        end = min(datetime.date(cur.year, 12, 31), yesterday)
        for it in fetch_range(cur, end):
            days[it["tm"]] = {
                "avg": num(it.get("avgTa")), "max": num(it.get("maxTa")),
                "min": num(it.get("minTa")), "rain": num(it.get("sumRn")),
            }
        print(f"{cur} ~ {end} 완료")
        cur = end + datetime.timedelta(days=1)

    store["days"] = dict(sorted(days.items()))
    store["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    print(f"총 {len(days)}일 저장")


if __name__ == "__main__":
    main()
