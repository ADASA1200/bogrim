"""מדמה את ימות המשיח מול השרת, לבדיקה בלי טלפון.
שימוש:  python simulate.py http://127.0.0.1:8080/yemot   (עם אותם משתני סביבה כמו השרת)"""
import os
import re
import sys
import uuid

import requests

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/yemot"
params = {"k": os.environ["URL_SECRET"], "ApiCallId": uuid.uuid4().hex,
          "ApiPhone": os.environ["OWNER_PHONE"]}

while True:
    body = requests.post(url, data=params, timeout=60).text
    print("\n<<< ימות מקבלת:", body)
    m = re.match(r"read=t-(.*?)=(\w+),", body)
    if not m:
        break
    print("🔊", m.group(1))
    params[m.group(2)] = input("אתה (הקלד מה היית אומר): ")
requests.post(url, data={**params, "hangup": "yes"}, timeout=10)
