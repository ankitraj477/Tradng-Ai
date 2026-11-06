import requests

token = "tradng-pro-2026"
headers = {"Authorization": f"Bearer {token}"}
url = "http://127.0.0.1:5000/api/capital-allocation"

res = requests.post(url, headers=headers, json={"intraday": 100, "swing": 0, "fno": 0})
print("POST status:", res.status_code)
print("POST payload:", res.json())

res_get = requests.get(url)
print("GET status:", res_get.status_code)
print("GET payload:", res_get.json())
