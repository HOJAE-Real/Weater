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
