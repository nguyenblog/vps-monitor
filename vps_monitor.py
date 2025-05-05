import os
import time
import psutil
import subprocess
import requests
from dotenv import load_dotenv
from datetime import datetime
import threading

# Load .env file from the script directory explicitly
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_USER_ID')
DISK_PATH = os.getenv('DISK_PATH', 'C:')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '3600'))
SCRIPTS_TO_MONITOR = [s.strip() for s in os.getenv('SCRIPTS_TO_MONITOR', '').split(',') if s.strip()]
PYTHON_PATH = os.getenv('PYTHON_PATH', 'python')

last_report_time = 0
last_update_id = 0
pending_restart = set()

def send_telegram_message(message):
    print(f"[DEBUG] BOT_TOKEN={BOT_TOKEN}, CHAT_ID={CHAT_ID}")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.ok:
            print(f"[LOG] Đã gửi báo cáo Telegram thành công.")
        else:
            print(f"[ERR] Gửi Telegram thất bại: {resp.text}")
    except Exception as e:
        print(f"[ERR] Lỗi gửi Telegram: {e}")

def check_disk_ram():
    disk = psutil.disk_usage(DISK_PATH)
    mem = psutil.virtual_memory()
    print(f"[LOG] Ổ đĩa ({DISK_PATH}): {disk.percent}% sử dụng, RAM: {mem.percent}% sử dụng")
    return disk, mem

def is_script_running(script_path):
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and isinstance(cmdline, (list, tuple)):
                if script_path in ' '.join(cmdline):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError):
            continue
    return False

def restart_script(script_path):
    try:
        print(f"[WARN] Script {script_path} không chạy. Đang khởi động lại...")
        if script_path.endswith('.py'):
            subprocess.Popen([PYTHON_PATH, script_path])
        elif script_path.endswith('.sh'):
            subprocess.Popen(['bash', script_path])
        else:
            subprocess.Popen([script_path])
        print(f"[LOG] Đã khởi động lại script: {script_path}")
        send_telegram_message(f"Đã khởi động lại script: {script_path}")
    except Exception as e:
        print(f"[ERR] Lỗi khi khởi động lại {script_path}: {e}")
        send_telegram_message(f"Lỗi khi khởi động lại {script_path}: {e}")

def stop_script(script_path):
    found = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and isinstance(cmdline, (list, tuple)):
                if script_path in ' '.join(cmdline):
                    proc.kill()
                    found = True
                    print(f"[LOG] Đã dừng process {proc.pid} cho script: {script_path}")
        except Exception as e:
            print(f"[ERR] Lỗi khi dừng process: {e}")
    return found

def get_script_status(script_name):
    if is_script_running(script_name):
        return f"✅ Script <code>{script_name}</code> đang <b>CHẠY</b>."
    else:
        return f"❌ Script <code>{script_name}</code> hiện <b>KHÔNG CHẠY</b>."

def check_reply_and_restart():
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    while True:
        try:
            params = {"timeout": 10, "offset": last_update_id + 1}
            resp = requests.get(url, params=params, timeout=15)
            if resp.ok:
                data = resp.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    message = update.get("message")
                    if not message:
                        continue
                    text = message.get("text", "").strip().lower()
                    if text.startswith("restart "):
                        script_name = text[8:].strip()
                        if script_name in SCRIPTS_TO_MONITOR:
                            if script_name not in pending_restart:
                                print(f"[LOG] Nhận lệnh restart script: {script_name} từ Telegram.")
                                restart_script(script_name)
                                send_telegram_message(f"Đã khởi động lại script: {script_name} theo yêu cầu.")
                                pending_restart.add(script_name)
                    elif text.startswith("stop "):
                        script_name = text[5:].strip()
                        if script_name in SCRIPTS_TO_MONITOR:
                            print(f"[LOG] Nhận lệnh stop script: {script_name} từ Telegram.")
                            stopped = stop_script(script_name)
                            if stopped:
                                send_telegram_message(f"Đã dừng script: {script_name} theo yêu cầu.")
                            else:
                                send_telegram_message(f"Không tìm thấy process nào đang chạy cho script: {script_name}.")
                    elif text.startswith("status "):
                        script_name = text[7:].strip()
                        if script_name in SCRIPTS_TO_MONITOR:
                            status_msg = get_script_status(script_name)
                            send_telegram_message(status_msg)
                        else:
                            send_telegram_message(f"Script <code>{script_name}</code> không nằm trong danh sách giám sát.")
            # Xóa pending sau 1 phút để cho phép restart lại nếu cần
            if pending_restart:
                time.sleep(60)
                pending_restart.clear()
            else:
                time.sleep(5)
        except Exception as e:
            print(f"[ERR] Lỗi check_reply_and_restart: {e}")
            time.sleep(5)

def monitor_scripts():
    status = []
    for script in SCRIPTS_TO_MONITOR:
        running = is_script_running(script)
        if running:
            print(f"[OK] Script {script} đang chạy.")
            status.append(f"{script}: Đang chạy")
        else:
            print(f"[ERR] Script {script} đã dừng!")
            msg = (
                f"<b>❌ Script <code>{script}</code> đã DỪNG!</b>\n"
                f"\n<b>👉 Để khởi động lại:</b> <code>restart {script}</code>"
                f"\n<b>👉 Để dừng hoàn toàn:</b> <code>stop {script}</code>"
            )
            send_telegram_message(msg)
            status.append(f"{script}: ĐÃ DỪNG - CHỜ XÁC NHẬN KHỞI ĐỘNG LẠI")
    return status

def build_report(disk, mem, script_status):
    report = f"<b>📊 VPS Monitor Report</b> <i>({datetime.now().strftime('%d/%m/%Y %H:%M:%S')})</i>\n"
    report += f"<b>💾 Ổ đĩa ({DISK_PATH}):</b> <code>{disk.percent}%</code> sử dụng (<code>{disk.used // (1024**3)}GB/{disk.total // (1024**3)}GB</code>)\n"
    report += f"<b>🧠 RAM:</b> <code>{mem.percent}%</code> sử dụng (<code>{mem.used // (1024**2)}MB/{mem.total // (1024**2)}MB</code>)\n"
    report += "\n<b>⚙️ Script quan trọng:</b>\n"
    for s in script_status:
        if 'Đang chạy' in s:
            report += f"✅ <code>{s}</code>\n"
        elif 'CHỜ XÁC NHẬN' in s:
            report += f"❌ <b>{s}</b>\n"
        else:
            report += f"⚠️ {s}\n"
    return report

def main():
    global last_report_time
    print("[LOG] Bắt đầu giám sát VPS...")
    # Chạy thread kiểm tra reply
    t = threading.Thread(target=check_reply_and_restart, daemon=True)
    t.start()
    while True:
        disk, mem = check_disk_ram()
        script_status = monitor_scripts()
        now = time.time()
        if now - last_report_time > CHECK_INTERVAL:
            print("[LOG] Đang gửi báo cáo Telegram...")
            report = build_report(disk, mem, script_status)
            send_telegram_message(report)
            last_report_time = now
        time.sleep(60)

if __name__ == "__main__":
    main()
