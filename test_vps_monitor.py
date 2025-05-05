import requests

BOT_TOKEN = "8033394940:AAHq0laV2foi3aJz8g5HmoJnoNnWR86-4Ys"
CHAT_ID = "5467697848"
url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(url, data={"chat_id": CHAT_ID, "text": "Test gửi từ VPS Monitor!"})
print(resp.text)